from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from threading import Event
from uuid import uuid7

import pytest
from sqlalchemy import Engine, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.session import SessionTransaction

from deepaha.acquisition.contracts import SourceRecipe
from deepaha.acquisition.models import AcquisitionEvaluation, AcquisitionRun
from deepaha.acquisition.official_evidence import (
    OfficialEvidenceAcquisitionError,
    OfficialEvidenceCommitOutcomeUnknown,
    OfficialEvidencePayloadDrift,
    OfficialEvidencePersistenceError,
    OfficialEvidenceRequest,
    OfficialEvidenceTask,
    OfficialEvidenceValidationError,
)
from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.object_store import ObjectMetadata
from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.core.settings import Settings
from deepaha.documents.models import Document, EvidenceRef, ParseAttempt
from deepaha.opportunities.models import Opportunity, OpportunityResolutionCandidate
from deepaha.p9b.models import SourceBundle, SourceBundleMember, SourceBundleRevision
from deepaha.sources.models import CaptureObservation, Source, SourceEndpoint
from deepaha.sources.transport import HttpRequest, HttpResponse, NetworkTransportError

pytestmark = pytest.mark.integration
NOW = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)
FIXTURE = Path(__file__).parents[1] / "fixtures" / "p10b1" / "official-notice.html"
VALID_BODY = FIXTURE.read_bytes()


class FixedClock:
    def now(self) -> datetime:
        return NOW


class NoSleep:
    def sleep(self, seconds: int) -> None:
        raise AssertionError(f"unexpected retry sleep: {seconds}")


class RecordingSleep:
    def __init__(self) -> None:
        self.seconds: list[int] = []

    def sleep(self, seconds: int) -> None:
        self.seconds.append(seconds)


class PublicResolver:
    def resolve(self, host: str) -> tuple[str, ...]:
        assert host == "official.example"
        return ("93.184.216.34",)


class ScriptedTransport:
    def __init__(self, script: list[HttpResponse | Exception]) -> None:
        self._script = iter(script)
        self.requests: list[HttpRequest] = []

    def get_once(self, request: HttpRequest) -> HttpResponse:
        self.requests.append(request)
        value = next(self._script)
        if isinstance(value, Exception):
            raise value
        return value


class SignalingTransport(ScriptedTransport):
    def __init__(self, script: list[HttpResponse | Exception], request_seen: Event) -> None:
        super().__init__(script)
        self._request_seen = request_seen

    def get_once(self, request: HttpRequest) -> HttpResponse:
        result = super().get_once(request)
        self._request_seen.set()
        return result


class BlockingTransport(ScriptedTransport):
    def __init__(self, script: list[HttpResponse | Exception]) -> None:
        super().__init__(script)
        self.entered = Event()
        self.release = Event()

    def get_once(self, request: HttpRequest) -> HttpResponse:
        self.entered.set()
        if not self.release.wait(timeout=5):
            raise AssertionError("blocking transport was not released")
        return super().get_once(request)


class ObservedStatStore:
    def __init__(self, delegate: S3ObjectStore, stat_seen: Event) -> None:
        self._delegate = delegate
        self._stat_seen = stat_seen

    def ensure_bucket(self) -> None:
        self._delegate.ensure_bucket()

    def put_bytes_if_absent(
        self,
        *,
        key: str,
        content: bytes,
        media_type: str | None,
        sha256: str,
    ) -> ObjectMetadata:
        return self._delegate.put_bytes_if_absent(
            key=key,
            content=content,
            media_type=media_type,
            sha256=sha256,
        )

    def get_bytes(self, *, key: str) -> bytes:
        return self._delegate.get_bytes(key=key)

    def stat(self, *, key: str) -> ObjectMetadata:
        return self._delegate.stat(key=key)

    def stat_if_present(self, *, key: str) -> ObjectMetadata | None:
        self._stat_seen.set()
        return self._delegate.stat_if_present(key=key)

    def delete_if_matches(self, *, key: str, sha256: str) -> bool:
        return self._delegate.delete_if_matches(key=key, sha256=sha256)


class FailAfterPutStore:
    def __init__(self, delegate: S3ObjectStore) -> None:
        self._delegate = delegate

    def ensure_bucket(self) -> None:
        self._delegate.ensure_bucket()

    def put_bytes_if_absent(
        self,
        *,
        key: str,
        content: bytes,
        media_type: str | None,
        sha256: str,
    ) -> ObjectMetadata:
        self._delegate.put_bytes_if_absent(
            key=key,
            content=content,
            media_type=media_type,
            sha256=sha256,
        )
        raise RuntimeError("synthetic post-upload failure")

    def get_bytes(self, *, key: str) -> bytes:
        return self._delegate.get_bytes(key=key)

    def stat(self, *, key: str) -> ObjectMetadata:
        return self._delegate.stat(key=key)

    def stat_if_present(self, *, key: str) -> ObjectMetadata | None:
        return self._delegate.stat_if_present(key=key)

    def delete_if_matches(self, *, key: str, sha256: str) -> bool:
        return self._delegate.delete_if_matches(key=key, sha256=sha256)


class FailingCleanupStore(FailAfterPutStore):
    def delete_if_matches(self, *, key: str, sha256: str) -> bool:
        raise RuntimeError("synthetic cleanup failure")


class LockInspectingFailAfterPutStore(FailAfterPutStore):
    def __init__(self, delegate: S3ObjectStore, factory: sessionmaker[Session]) -> None:
        super().__init__(delegate)
        self._factory = factory
        self.content_lock_was_available: bool | None = None

    def delete_if_matches(self, *, key: str, sha256: str) -> bool:
        with self._factory.begin() as session:
            self.content_lock_was_available = bool(
                session.scalar(
                    text("select pg_try_advisory_xact_lock(hashtextextended(:content_sha256, 1))"),
                    {"content_sha256": sha256},
                )
            )
        return super().delete_if_matches(key=key, sha256=sha256)


class CorruptingReadStore(ObservedStatStore):
    def __init__(self, delegate: S3ObjectStore) -> None:
        super().__init__(delegate, Event())

    def get_bytes(self, *, key: str) -> bytes:
        return super().get_bytes(key=key) + b"corrupt"


@pytest.fixture(scope="module")
def object_store() -> S3ObjectStore:
    value = S3ObjectStore(Settings())
    value.ensure_bucket()
    return value


@pytest.fixture
def factory(migrated_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=migrated_engine, expire_on_commit=False)


def seed_policy(
    factory: sessionmaker[Session],
    *,
    max_attempts: int = 1,
) -> tuple[SourceEndpoint, SourceRecipe]:
    source_id = uuid7()
    endpoint_id = uuid7()
    source = Source(
        source_id=source_id,
        public_id=f"src_{source_id.hex}",
        canonical_url=f"https://official.example/source/{source_id.hex}",
        authority_name="Synthetic official authority",
        tier="OFFICIAL_PRIMARY",
        jurisdiction=None,
        active=True,
        created_at=NOW,
        updated_at=NOW,
    )
    endpoint = SourceEndpoint(
        endpoint_id=endpoint_id,
        source_id=source_id,
        url="https://official.example/notices/1",
        allowed_hosts=["official.example"],
        expected_media_types=["text/html"],
        browser_policy="NEVER",
        minimum_interval_seconds=60,
        timeout_seconds=20,
        max_attempts=max_attempts,
        robots_url="https://official.example/robots.txt",
        robots_decision="ALLOWED",
        robots_checked_at=NOW,
        content_use_basis="OFFICIAL_PUBLIC_ACCESS",
        license_name=None,
        license_url=None,
        attribution="Synthetic official authority",
        fixture_storage_allowed=False,
        usage_note="Synthetic P10-B1 integration fixture.",
        policy_version="2026-09-01.1",
        active=True,
        verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    with factory.begin() as session:
        session.add_all([source, endpoint])
    recipe_id = uuid7()
    recipe = SourceRecipe.model_validate(
        {
            "recipe_id": recipe_id,
            "source_id": source_id,
            "endpoint_id": endpoint_id,
            "endpoint_policy_version": endpoint.policy_version,
            "recipe_version": "2026-09-01.1",
            "usage_role": "PRIMARY_EVIDENCE",
            "allowed_hosts": endpoint.allowed_hosts,
            "expected_media_types": endpoint.expected_media_types,
            "allowed_url_patterns": ["/notices/*"],
            "fetch_plan": [{"strategy": "STATIC_HTTP", "fallback_on": []}],
            "expectations": {
                "minimum_bytes": 20,
                "maximum_bytes": 100_000,
                "required_markers": ["official notice"],
                "forbidden_markers": ["captcha"],
                "required_selectors": ["main"],
                "minimum_discovered_count": None,
                "structured_kind": None,
                "contract_version": "1.0.0",
            },
            "discovery": {
                "kind": "NONE",
                "item_selector": None,
                "detail_link_selector": None,
                "attachment_link_selector": None,
                "pagination_link_selector": None,
                "structured_items_path": [],
                "detail_limit": 0,
                "attachment_limit": 0,
                "pagination_limit": 0,
            },
            "maximum_requests": 1,
            "maximum_elapsed_seconds": 30,
            "health": {
                "expected_change_frequency": "IRREGULAR",
                "zero_discovery_grace_runs": 0,
                "consecutive_failure_limit": 1,
                "selector_drift_grace_runs": 0,
            },
            "active": True,
            "verified_at": NOW,
            "contract_version": "1.0.0",
        }
    )
    return endpoint, recipe


def capture_request(endpoint: SourceEndpoint, recipe: SourceRecipe) -> OfficialEvidenceRequest:
    return OfficialEvidenceRequest.model_validate(
        {
            "request_key": f"synthetic:{endpoint.endpoint_id.hex}:1",
            "source_id": endpoint.source_id,
            "endpoint_id": endpoint.endpoint_id,
            "recipe_id": recipe.recipe_id,
            "requested_url": endpoint.url,
            "contract_version": "1.0.0",
        }
    )


def response(
    body: bytes = VALID_BODY,
    *,
    media_type: str = "text/html; charset=utf-8",
    url: str = "https://official.example/notices/1",
    status_code: int = 200,
    location: str | None = None,
) -> HttpResponse:
    return HttpResponse(
        status_code=status_code,
        url=url,
        media_type=media_type,
        etag='"synthetic-etag"',
        last_modified="Mon, 01 Sep 2026 08:00:00 GMT",
        location=location,
        body=body,
    )


def task(
    *,
    factory: sessionmaker[Session],
    object_store: (
        S3ObjectStore
        | FailAfterPutStore
        | LockInspectingFailAfterPutStore
        | ObservedStatStore
        | CorruptingReadStore
    ),
    recipe: SourceRecipe | tuple[SourceRecipe, ...],
    transport: ScriptedTransport,
    sleeper: NoSleep | RecordingSleep | None = None,
) -> OfficialEvidenceTask:
    return OfficialEvidenceTask(
        session_factory=factory,
        object_store=object_store,
        recipes=recipe if isinstance(recipe, tuple) else (recipe,),
        transport=transport,
        resolver=PublicResolver(),
        clock=FixedClock(),
        sleeper=sleeper or NoSleep(),
    )


def formal_counts(session: Session) -> dict[str, int]:
    models = (
        RawArtifact,
        CaptureObservation,
        AcquisitionEvaluation,
        AcquisitionRun,
        Document,
        ParseAttempt,
        EvidenceRef,
        SourceBundle,
        SourceBundleRevision,
        SourceBundleMember,
    )
    return {
        model.__tablename__: session.scalar(select(func.count()).select_from(model)) or 0
        for model in models
    }


def test_capture_persists_complete_frozen_raw_evidence_and_exact_replay_is_zero_delta(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    transport = ScriptedTransport([response()])
    runner = task(
        factory=factory,
        object_store=object_store,
        recipe=configured_recipe,
        transport=transport,
    )
    request = capture_request(endpoint, configured_recipe)

    first = runner.run(request)
    with factory() as session:
        before = formal_counts(session)
        bundle = session.get(SourceBundle, first.source_bundle_id)
        revision = session.get(SourceBundleRevision, first.source_bundle_revision_id)
        artifact = session.get(RawArtifact, first.raw_artifact_id)
        evidence = session.get(EvidenceRef, first.evidence_ref_id)
        member = session.scalar(
            select(SourceBundleMember).where(
                SourceBundleMember.source_bundle_revision_id == first.source_bundle_revision_id
            )
        )
        parse_attempt = session.scalar(
            select(ParseAttempt).where(ParseAttempt.document_id == first.document_id)
        )
        assert bundle is not None
        assert bundle.opportunity_id is None
        assert bundle.request_key == request.request_key
        assert revision is not None and revision.status == "FROZEN"
        assert revision.opportunity_id is None and revision.opportunity_version is None
        assert artifact is not None
        assert artifact.content_sha256 == sha256(VALID_BODY).hexdigest()
        assert artifact.retrieved_at == NOW
        assert evidence is not None
        assert member is not None
        assert parse_attempt is not None
        assert member.evidence_ref_id == evidence.evidence_ref_id
        assert member.parse_attempt_id == parse_attempt.parse_attempt_id
        assert (evidence.locator_kind, evidence.locator_value) == ("full_document", "*")
        assert evidence.quote_sha256 == artifact.content_sha256
        assert session.scalar(select(func.count()).select_from(Opportunity)) == 0
        assert session.scalar(select(func.count()).select_from(OpportunityResolutionCandidate)) == 0
    assert object_store.get_bytes(key=first.object_key) == VALID_BODY

    replay = runner.run(request)
    with factory() as session:
        assert formal_counts(session) == before
    assert replay.model_copy(update={"replayed": False}) == first
    assert replay.replayed is True
    assert len(transport.requests) == 1


def test_payload_drift_is_rejected_before_transport_or_storage(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    transport = ScriptedTransport([response()])
    runner = task(
        factory=factory,
        object_store=object_store,
        recipe=configured_recipe,
        transport=transport,
    )
    request = capture_request(endpoint, configured_recipe)
    first = runner.run(request)
    with factory() as session:
        before = formal_counts(session)
    drifted = OfficialEvidenceRequest.model_validate(
        {**request.model_dump(mode="json"), "requested_url": "https://official.example/notices/2"}
    )

    with pytest.raises(OfficialEvidencePayloadDrift, match="OFFICIAL_EVIDENCE_PAYLOAD_DRIFT"):
        runner.run(drifted)

    with factory() as session:
        assert formal_counts(session) == before
    assert len(transport.requests) == 1
    assert object_store.get_bytes(key=first.object_key) == VALID_BODY


def test_new_request_key_cannot_bypass_endpoint_rate_limit(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    transport = ScriptedTransport([response()])
    runner = task(
        factory=factory,
        object_store=object_store,
        recipe=configured_recipe,
        transport=transport,
    )
    first_request = capture_request(endpoint, configured_recipe)
    runner.run(first_request)
    with factory() as session:
        before = formal_counts(session)
    second_request = OfficialEvidenceRequest.model_validate(
        {**first_request.model_dump(mode="json"), "request_key": f"{first_request.request_key}:2"}
    )

    with pytest.raises(
        OfficialEvidenceAcquisitionError,
        match="RATE_LIMIT_NOT_ELAPSED",
    ):
        runner.run(second_request)

    with factory() as session:
        assert formal_counts(session) == before
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    "script",
    ([response(b"<main>unrelated page</main>")], [NetworkTransportError()]),
)
def test_acquisition_or_validation_failure_leaves_no_formal_rows_or_object(
    factory: sessionmaker[Session],
    object_store: S3ObjectStore,
    script: list[HttpResponse | Exception],
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    runner = task(
        factory=factory,
        object_store=object_store,
        recipe=configured_recipe,
        transport=ScriptedTransport(script),
    )

    with pytest.raises((OfficialEvidenceValidationError, OfficialEvidenceAcquisitionError)):
        runner.run(capture_request(endpoint, configured_recipe))

    with factory() as session:
        assert set(formal_counts(session).values()) == {0}
    first_attempt = script[0]
    if isinstance(first_attempt, HttpResponse):
        digest = sha256(first_attempt.body).hexdigest()
        assert object_store.stat_if_present(key=f"raw/sha256/{digest[:2]}/{digest}") is None


def test_recipe_single_request_budget_overrides_endpoint_retry_policy(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint, configured_recipe = seed_policy(factory, max_attempts=3)
    transport = ScriptedTransport([NetworkTransportError(), response()])
    sleeper = RecordingSleep()
    runner = task(
        factory=factory,
        object_store=object_store,
        recipe=configured_recipe,
        transport=transport,
        sleeper=sleeper,
    )

    with pytest.raises(OfficialEvidenceAcquisitionError):
        runner.run(capture_request(endpoint, configured_recipe))

    assert len(transport.requests) == 1
    assert sleeper.seconds == []


def test_recipe_single_request_budget_does_not_follow_redirects(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    transport = ScriptedTransport(
        [
            response(
                body=b"redirect",
                status_code=302,
                location="/notices/2",
            ),
            response(url="https://official.example/notices/2"),
        ]
    )
    runner = task(
        factory=factory,
        object_store=object_store,
        recipe=configured_recipe,
        transport=transport,
    )

    with pytest.raises(OfficialEvidenceAcquisitionError):
        runner.run(capture_request(endpoint, configured_recipe))

    assert len(transport.requests) == 1


def test_exact_mime_whitelist_is_enforced_before_content_validation(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    runner = task(
        factory=factory,
        object_store=object_store,
        recipe=configured_recipe,
        transport=ScriptedTransport([response(media_type="application/xhtml+xml; charset=utf-8")]),
    )

    with pytest.raises(OfficialEvidenceAcquisitionError, match="MEDIA_TYPE_NOT_ALLOWED"):
        runner.run(capture_request(endpoint, configured_recipe))

    with factory() as session:
        assert set(formal_counts(session).values()) == {0}


def test_same_source_and_content_reuses_raw_artifact_across_capture_urls(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    first_endpoint, first_recipe = seed_policy(factory)
    second_endpoint_id = uuid7()
    second_endpoint = SourceEndpoint(
        endpoint_id=second_endpoint_id,
        source_id=first_endpoint.source_id,
        url="https://official.example/notices/2",
        allowed_hosts=list(first_endpoint.allowed_hosts),
        expected_media_types=list(first_endpoint.expected_media_types),
        browser_policy=first_endpoint.browser_policy,
        minimum_interval_seconds=first_endpoint.minimum_interval_seconds,
        timeout_seconds=first_endpoint.timeout_seconds,
        max_attempts=first_endpoint.max_attempts,
        robots_url=first_endpoint.robots_url,
        robots_decision=first_endpoint.robots_decision,
        robots_checked_at=first_endpoint.robots_checked_at,
        content_use_basis=first_endpoint.content_use_basis,
        license_name=first_endpoint.license_name,
        license_url=first_endpoint.license_url,
        attribution=first_endpoint.attribution,
        fixture_storage_allowed=first_endpoint.fixture_storage_allowed,
        usage_note=first_endpoint.usage_note,
        policy_version=first_endpoint.policy_version,
        active=True,
        verified_at=first_endpoint.verified_at,
        created_at=NOW,
        updated_at=NOW,
    )
    second_recipe = first_recipe.model_copy(
        update={"recipe_id": uuid7(), "endpoint_id": second_endpoint_id}
    )
    with factory.begin() as session:
        session.add(second_endpoint)
    transport = ScriptedTransport([response(), response(url="https://official.example/notices/2")])
    runner = task(
        factory=factory,
        object_store=object_store,
        recipe=(first_recipe, second_recipe),
        transport=transport,
    )

    first = runner.run(capture_request(first_endpoint, first_recipe))
    second = runner.run(capture_request(second_endpoint, second_recipe))

    assert second.raw_artifact_id == first.raw_artifact_id
    assert second.retrieved_at == NOW
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(RawArtifact)) == 1
        observations = session.scalars(
            select(CaptureObservation)
            .where(CaptureObservation.artifact_id == first.raw_artifact_id)
            .order_by(CaptureObservation.requested_url)
        ).all()
        assert [value.requested_url for value in observations] == [
            "https://official.example/notices/1",
            "https://official.example/notices/2",
        ]


def test_frozen_request_member_protects_exact_evidence_and_parse_attempt(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    result = task(
        factory=factory,
        object_store=object_store,
        recipe=configured_recipe,
        transport=ScriptedTransport([response()]),
    ).run(capture_request(endpoint, configured_recipe))
    with factory() as session:
        member = session.scalar(
            select(SourceBundleMember).where(
                SourceBundleMember.source_bundle_revision_id == result.source_bundle_revision_id
            )
        )
        assert member is not None
        evidence_ref_id = member.evidence_ref_id
        parse_attempt_id = member.parse_attempt_id

    with (
        pytest.raises(DBAPIError, match="P10B1_BOUND_EVIDENCE_REF_IMMUTABLE"),
        factory.begin() as session,
    ):
        session.execute(
            text(
                "update evidence_refs set quote_sha256 = :digest "
                "where evidence_ref_id = :evidence_ref_id"
            ),
            {"digest": "b" * 64, "evidence_ref_id": evidence_ref_id},
        )
    with (
        pytest.raises(DBAPIError, match="P10B1_BOUND_PARSE_ATTEMPT_IMMUTABLE"),
        factory.begin() as session,
    ):
        session.execute(
            text(
                "update parse_attempts set completed_at = completed_at + interval '1 second' "
                "where parse_attempt_id = :parse_attempt_id"
            ),
            {"parse_attempt_id": parse_attempt_id},
        )


def test_replay_verifies_actual_object_bytes_not_only_metadata(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    request = capture_request(endpoint, configured_recipe)
    task(
        factory=factory,
        object_store=object_store,
        recipe=configured_recipe,
        transport=ScriptedTransport([response()]),
    ).run(request)
    replay_runner = task(
        factory=factory,
        object_store=CorruptingReadStore(object_store),
        recipe=configured_recipe,
        transport=ScriptedTransport([]),
    )

    with pytest.raises(OfficialEvidencePersistenceError):
        replay_runner.run(request)


def test_post_upload_failure_rolls_back_rows_and_compensates_new_object(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    digest = sha256(VALID_BODY).hexdigest()
    object_key = f"raw/sha256/{digest[:2]}/{digest}"
    object_store.delete_if_matches(key=object_key, sha256=digest)
    runner = task(
        factory=factory,
        object_store=FailAfterPutStore(object_store),
        recipe=configured_recipe,
        transport=ScriptedTransport([response()]),
    )

    with pytest.raises(OfficialEvidencePersistenceError) as caught:
        runner.run(capture_request(endpoint, configured_recipe))

    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True

    with factory() as session:
        assert set(formal_counts(session).values()) == {0}
    assert object_store.stat_if_present(key=object_key) is None


def test_commit_outcome_unknown_never_compensates_the_content_object(
    factory: sessionmaker[Session],
    object_store: S3ObjectStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    request = capture_request(endpoint, configured_recipe)
    runner = task(
        factory=factory,
        object_store=object_store,
        recipe=configured_recipe,
        transport=ScriptedTransport([response()]),
    )
    original_commit = SessionTransaction.commit

    def commit_then_report_unknown(transaction: SessionTransaction) -> None:
        is_root_transaction = transaction.parent is None
        original_commit(transaction)
        if is_root_transaction:
            raise RuntimeError("synthetic commit result unknown")

    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(SessionTransaction, "commit", commit_then_report_unknown)
        with pytest.raises(OfficialEvidenceCommitOutcomeUnknown) as caught:
            runner.run(request)

    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
    digest = sha256(VALID_BODY).hexdigest()
    object_key = f"raw/sha256/{digest[:2]}/{digest}"
    assert object_store.get_bytes(key=object_key) == VALID_BODY
    replay = runner.run(request)
    assert replay.replayed is True


def test_content_existence_check_waits_for_the_content_hash_lock(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    request_seen = Event()
    stat_seen = Event()
    transport = SignalingTransport([response()], request_seen)
    runner = task(
        factory=factory,
        object_store=ObservedStatStore(object_store, stat_seen),
        recipe=configured_recipe,
        transport=transport,
    )
    digest = sha256(VALID_BODY).hexdigest()

    with ThreadPoolExecutor(max_workers=1) as executor:
        with factory.begin() as blocker:
            blocker.execute(
                text("select pg_advisory_xact_lock(hashtextextended(:content_sha256, 1))"),
                {"content_sha256": digest},
            )
            future = executor.submit(runner.run, capture_request(endpoint, configured_recipe))
            assert request_seen.wait(timeout=2)
            assert not stat_seen.wait(timeout=0.2)
        result = future.result(timeout=5)

    assert stat_seen.is_set()
    assert result.content_sha256 == digest


def test_post_upload_compensation_runs_before_content_hash_lock_is_released(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    digest = sha256(VALID_BODY).hexdigest()
    object_key = f"raw/sha256/{digest[:2]}/{digest}"
    object_store.delete_if_matches(key=object_key, sha256=digest)
    inspecting_store = LockInspectingFailAfterPutStore(object_store, factory)
    runner = task(
        factory=factory,
        object_store=inspecting_store,
        recipe=configured_recipe,
        transport=ScriptedTransport([response()]),
    )

    with pytest.raises(OfficialEvidencePersistenceError) as caught:
        runner.run(capture_request(endpoint, configured_recipe))

    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
    assert inspecting_store.content_lock_was_available is False
    assert object_store.stat_if_present(key=object_key) is None


def test_cleanup_failure_uses_stable_error_without_exposing_the_store_error(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    digest = sha256(VALID_BODY).hexdigest()
    object_key = f"raw/sha256/{digest[:2]}/{digest}"
    object_store.delete_if_matches(key=object_key, sha256=digest)
    runner = task(
        factory=factory,
        object_store=FailingCleanupStore(object_store),
        recipe=configured_recipe,
        transport=ScriptedTransport([response()]),
    )

    with pytest.raises(OfficialEvidencePersistenceError) as caught:
        runner.run(capture_request(endpoint, configured_recipe))

    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
    with factory() as session:
        assert set(formal_counts(session).values()) == {0}
    assert object_store.stat_if_present(key=object_key) is not None
    object_store.delete_if_matches(key=object_key, sha256=digest)


def test_rollback_failure_uses_stable_error_without_exposing_database_details(
    factory: sessionmaker[Session],
    object_store: S3ObjectStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    digest = sha256(VALID_BODY).hexdigest()
    object_key = f"raw/sha256/{digest[:2]}/{digest}"
    object_store.delete_if_matches(key=object_key, sha256=digest)
    runner = task(
        factory=factory,
        object_store=FailAfterPutStore(object_store),
        recipe=configured_recipe,
        transport=ScriptedTransport([response()]),
    )
    original_rollback = SessionTransaction.rollback

    def rollback_then_fail(
        transaction: SessionTransaction,
        _capture_exception: bool = False,
        _to_root: bool = False,
    ) -> None:
        original_rollback(transaction, _capture_exception, _to_root)
        raise RuntimeError("synthetic rollback failure")

    with monkeypatch.context() as scoped_patch:
        scoped_patch.setattr(SessionTransaction, "rollback", rollback_then_fail)
        with pytest.raises(OfficialEvidencePersistenceError) as caught:
            runner.run(capture_request(endpoint, configured_recipe))

    assert caught.value.__cause__ is None
    assert caught.value.__suppress_context__ is True
    with factory() as session:
        assert set(formal_counts(session).values()) == {0}
    assert object_store.stat_if_present(key=object_key) is None


def test_concurrent_payload_drift_waits_for_request_lock_before_transport(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    first_transport = BlockingTransport([response()])
    second_transport = BlockingTransport([response()])
    first_runner = task(
        factory=factory,
        object_store=object_store,
        recipe=configured_recipe,
        transport=first_transport,
    )
    second_runner = task(
        factory=factory,
        object_store=object_store,
        recipe=configured_recipe,
        transport=second_transport,
    )
    first_request = capture_request(endpoint, configured_recipe)
    drifted = OfficialEvidenceRequest.model_validate(
        {
            **first_request.model_dump(mode="json"),
            "requested_url": "https://official.example/notices/2",
        }
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(first_runner.run, first_request)
        assert first_transport.entered.wait(timeout=2)
        second_future = executor.submit(second_runner.run, drifted)
        try:
            assert not second_transport.entered.wait(timeout=0.2)
        finally:
            first_transport.release.set()
            second_transport.release.set()
        first_future.result(timeout=5)
        with pytest.raises(OfficialEvidencePayloadDrift):
            second_future.result(timeout=5)

    assert len(first_transport.requests) == 1
    assert second_transport.requests == []


def test_concurrent_request_keys_wait_for_endpoint_lock_before_transport(
    factory: sessionmaker[Session], object_store: S3ObjectStore
) -> None:
    endpoint, configured_recipe = seed_policy(factory)
    first_transport = BlockingTransport([response()])
    second_transport = BlockingTransport([response()])
    first_runner = task(
        factory=factory,
        object_store=object_store,
        recipe=configured_recipe,
        transport=first_transport,
    )
    second_runner = task(
        factory=factory,
        object_store=object_store,
        recipe=configured_recipe,
        transport=second_transport,
    )
    first_request = capture_request(endpoint, configured_recipe)
    second_request = OfficialEvidenceRequest.model_validate(
        {**first_request.model_dump(mode="json"), "request_key": f"{first_request.request_key}:2"}
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(first_runner.run, first_request)
        assert first_transport.entered.wait(timeout=2)
        second_future = executor.submit(second_runner.run, second_request)
        try:
            assert not second_transport.entered.wait(timeout=0.2)
        finally:
            first_transport.release.set()
            second_transport.release.set()
        first_future.result(timeout=5)
        with pytest.raises(OfficialEvidenceAcquisitionError, match="RATE_LIMIT_NOT_ELAPSED"):
            second_future.result(timeout=5)

    assert len(first_transport.requests) == 1
    assert second_transport.requests == []

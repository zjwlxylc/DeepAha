"""Exclusion of unparseable official materials: unit tests only, never a database.

These tests deliberately stay away from PostgreSQL. The rows are doubled by small fakes
because every guarded branch here is a *decision* ("may this reviewer exclude this material
right now"), and a decision must be testable without the persistence that merely records it.
"""

import dataclasses
from collections import deque
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid7

import pytest

from deepaha.artifacts.models import RawArtifact
from deepaha.documents.opaque import OpaqueBinaryParser
from deepaha.documents.parser import P9B_BLOCK_PARSE_CONTRACT_VERSION, DocumentParser
from deepaha.investigations.contracts import InvestigationError
from deepaha.investigations.document_exclusions import exclude_document, revoke_exclusion
from deepaha.investigations.documents import _parser_for, describe_documents, document_parsers
from deepaha.investigations.models import (
    InvestigationDocumentExclusion,
    InvestigationMaterial,
    InvestigationTask,
)
from deepaha.investigations.store import InvestigationStore
from deepaha.review.auth import (
    OPPORTUNITY_FACT_VALIDATION_PURPOSE,
    ReviewerAuthenticationError,
    ReviewerPrincipal,
    ReviewerRole,
)
from deepaha.review.models import ReviewerAccountModel

TASK_ID = UUID("019c0000-0000-7000-8000-000000000901")
ARTIFACT_ID = UUID("019c0000-0000-7000-8000-000000000902")
REVIEWER_ID = UUID("019c0000-0000-7000-8000-000000000903")
DOCUMENT_ID = UUID("019c0000-0000-7000-8000-000000000904")
ATTEMPT_ID = UUID("019c0000-0000-7000-8000-000000000905")

HTML_MEDIA_TYPE = "text/html"
PDF_MEDIA_TYPE = "application/pdf"
LEGACY_MEDIA_TYPE = "application/msword"
DELIVERY_HASH = "a" * 64
REASON = "legacy .doc has no machine-readable text; excluded by hand"
REVOCATION = "superseded by a re-collected delivery"


def _html_parser() -> DocumentParser:
    parser = _parser_for(HTML_MEDIA_TYPE, document_parsers())
    assert parser is not None, "fixtures assume an html-capable parser is registered"
    return parser


HTML_PARSER = _html_parser()


@dataclasses.dataclass
class _Task:
    task_id: UUID = TASK_ID
    status: str = "PENDING_REVIEW"
    delivery_hash: str = DELIVERY_HASH


@dataclasses.dataclass
class _Account:
    reviewer_id: UUID = REVIEWER_ID
    roles: list[str] = dataclasses.field(default_factory=lambda: ["LOCAL_TEST_OPERATOR"])
    allowed_purposes: list[str] = dataclasses.field(
        default_factory=lambda: [OPPORTUNITY_FACT_VALIDATION_PURPOSE]
    )
    synthetic: bool = False
    active: bool = True


@dataclasses.dataclass
class _Raw:
    artifact_id: UUID = ARTIFACT_ID
    media_type: str = LEGACY_MEDIA_TYPE


@dataclasses.dataclass
class _Attempt:
    """Only the attributes ``describe_documents`` reads."""

    outcome: str
    error_code: str | None = None
    document_id: UUID | None = None
    parse_attempt_id: UUID = ATTEMPT_ID
    document_parse_key: str = "synthetic-key"
    artifact_id: UUID = ARTIFACT_ID
    parser_name: str = ""
    parser_version: str = ""
    parse_contract_version: str = ""


class _FakeSession:
    """Session double answering the exact queries the exclusion flow issues, in order.

    Exclusion rows are filtered on ``revoked_at is None`` by hand, because in the real
    query that predicate lives in SQL and therefore never reaches Python.
    """

    def __init__(
        self,
        *,
        task: _Task | None = None,
        account: _Account | None = None,
        raw: _Raw | None = None,
        entities: dict[type, list[list[Any]]] | None = None,
        scalars: list[Any] | None = None,
    ) -> None:
        self._resolved: dict[type, Any] = {
            InvestigationTask: task,
            ReviewerAccountModel: account,
            RawArtifact: raw,
        }
        self._entities = {key: deque(value) for key, value in (entities or {}).items()}
        self._scalars = deque(scalars or [])
        self.added: list[Any] = []

    def begin(self) -> _FakeSession:
        return self

    def __enter__(self) -> _FakeSession:
        return self

    def __exit__(self, *info: object) -> None:
        return None

    def resolve(self, model: type, row: Any) -> None:
        self._resolved[model] = row

    def get(self, model: type, key: object) -> Any:
        return self._resolved.get(model)

    def scalars(self, statement: Any) -> list[Any]:
        entity = cast(type, statement.column_descriptions[0]["entity"])
        queue = self._entities.setdefault(entity, deque())
        rows = list(queue.popleft()) if queue else []
        if entity is InvestigationDocumentExclusion:
            return [row for row in rows if row.revoked_at is None]
        return rows

    def scalar(self, statement: Any) -> Any:
        return self._scalars.popleft() if self._scalars else None

    def add(self, row: Any) -> None:
        self.added.append(row)


class _FakeStore:
    """Store double exposing only what the exclusion flow touches."""

    def __init__(self, session: _FakeSession, task: _Task) -> None:
        self._session = session
        self._task = task
        self.view = {"task_id": str(task.task_id), "status": task.status}

    def factory(self) -> _FakeSession:
        return self._session

    def clock(self) -> datetime:
        return datetime(2026, 9, 11, 12, 0, tzinfo=UTC)

    def _get(self, session: _FakeSession, task_id: UUID, *, lock: bool = False) -> _Task:
        assert task_id == self._task.task_id
        return self._task

    def _view(self, session: _FakeSession, task: _Task) -> dict[str, Any]:
        return dict(self.view)


def _material(material_id: str, media_type: str) -> InvestigationMaterial:
    return InvestigationMaterial(
        task_id=TASK_ID,
        material_id=material_id,
        raw_artifact_id=ARTIFACT_ID,
        metadata_snapshot={"media_type": media_type, "sha256": "0" * 64},
    )


def _exclusion(**overrides: Any) -> InvestigationDocumentExclusion:
    defaults: dict[str, Any] = {
        "exclusion_id": uuid7(),
        "task_id": TASK_ID,
        "material_id": "legacy.doc",
        "raw_artifact_id": ARTIFACT_ID,
        "media_type": LEGACY_MEDIA_TYPE,
        "delivery_hash": DELIVERY_HASH,
        "reason": REASON,
        "excluded_by": REVIEWER_ID,
        "excluded_at": datetime(2026, 9, 11, 9, 0, tzinfo=UTC),
        "revoked_at": None,
        "revoked_by": None,
        "revoked_reason": None,
    }
    return InvestigationDocumentExclusion(**defaults | overrides)


def _principal(
    roles: frozenset[ReviewerRole] = frozenset({ReviewerRole.LOCAL_TEST_OPERATOR}),
) -> ReviewerPrincipal:
    return ReviewerPrincipal(
        REVIEWER_ID, roles, frozenset({OPPORTUNITY_FACT_VALIDATION_PURPOSE}), False
    )


def _html_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "material_id": "notice",
        "outcome": "SUCCEEDED",
        "error_code": None,
        "document_id": str(DOCUMENT_ID),
        "parse_attempt_id": str(ATTEMPT_ID),
        "document_parse_key": "synthetic-key",
        "parser_name": HTML_PARSER.name,
        "parser_version": HTML_PARSER.version,
        "parse_contract_version": HTML_PARSER.parse_contract_version,
        "block_count": 2,
        "evidence_ref_count": 2,
        "excluded": False,
        "evidence_mode": "TEXT",
        "exclusion": None,
    }
    return row | overrides


def _legacy_row_unsupported() -> dict[str, Any]:
    return {
        "material_id": "legacy.doc",
        "outcome": "UNSUPPORTED",
        "error_code": "DOCUMENT_FORMAT_UNSUPPORTED",
        "document_id": None,
        "parse_attempt_id": None,
        "document_parse_key": None,
        "parser_name": None,
        "parser_version": None,
        "parse_contract_version": None,
        "block_count": 0,
        "evidence_ref_count": 0,
        "excluded": False,
        "evidence_mode": None,  # nothing was parsed, so there is no text to point at
        "exclusion": None,
    }


def test_describe_documents_without_exclusions_keeps_the_legacy_shape() -> None:
    """Guard the existing assertions: nothing changes when nothing is excluded."""
    materials = [_material("legacy.doc", LEGACY_MEDIA_TYPE), _material("notice", HTML_MEDIA_TYPE)]
    attempt = _Attempt(outcome="SUCCEEDED", document_id=DOCUMENT_ID)
    session = _FakeSession(
        task=_Task(),
        entities={InvestigationDocumentExclusion: [[]]},
        scalars=[attempt, 2, 2],
    )

    result = describe_documents(cast(Any, session), materials)

    assert result == {
        "scope": "DOCUMENT_EVIDENCE_ONLY",
        "status": "NEEDS_ATTENTION",
        "material_count": 2,
        "prepared_count": 1,
        "excluded_count": 0,
        "unsupported_count": 1,
        "materials": [_legacy_row_unsupported(), _html_row()],
    }


def test_evidence_mode_only_marks_materials_that_really_hold_text() -> None:
    """UNSUPPORTED, FAILED and "succeeded with no blocks" must not claim TEXT."""
    materials = [
        _material("notice", HTML_MEDIA_TYPE),
        _material("legacy.doc", LEGACY_MEDIA_TYPE),
        _material("broken.pdf", PDF_MEDIA_TYPE),
        _material("empty.pdf", PDF_MEDIA_TYPE),
    ]
    session = _FakeSession(
        task=_Task(),
        entities={InvestigationDocumentExclusion: [[]]},
        scalars=[
            _Attempt(outcome="SUCCEEDED", document_id=DOCUMENT_ID),  # notice
            2,
            2,
            _Attempt(outcome="FAILED", error_code="READER_NO_TEXT"),  # broken.pdf
            _Attempt(outcome="SUCCEEDED", document_id=DOCUMENT_ID),  # empty.pdf, no blocks
            0,
            0,
        ],
    )

    modes = {
        row["material_id"]: (row["outcome"], row["evidence_mode"])
        for row in describe_documents(cast(Any, session), materials)["materials"]
    }

    assert modes == {
        "notice": ("SUCCEEDED", "TEXT"),
        "legacy.doc": ("UNSUPPORTED", None),
        "broken.pdf": ("FAILED", None),
        # Downgraded after the fact, so it must not advertise text either.
        "empty.pdf": ("NEEDS_REVIEW", None),
    }


def test_excluded_material_parsed_by_a_real_parser_keeps_the_text_mode() -> None:
    """If a later deployment can parse an excluded file, its blocks are real text."""
    materials = [_material("terms.pdf", PDF_MEDIA_TYPE)]
    session = _FakeSession(
        task=_Task(),
        entities={InvestigationDocumentExclusion: [[_exclusion(material_id="terms.pdf")]]},
        scalars=[_Attempt(outcome="SUCCEEDED", document_id=DOCUMENT_ID), 2, 2],
    )

    row = describe_documents(cast(Any, session), materials)["materials"][0]

    assert row["excluded"] is True
    assert row["outcome"] == "SUCCEEDED"
    assert row["evidence_mode"] == "TEXT"


def test_excluded_material_reaches_opaque_prepared_state() -> None:
    """After the opaque parse the row is prepared but carries no quotable text."""
    materials = [_material("legacy.doc", LEGACY_MEDIA_TYPE), _material("notice", HTML_MEDIA_TYPE)]
    opaque = OpaqueBinaryParser(frozenset({LEGACY_MEDIA_TYPE}))
    legacy_attempt = _Attempt(
        outcome="SUCCEEDED",
        document_id=DOCUMENT_ID,
        parser_name=opaque.name,
        parser_version=opaque.version,
        parse_contract_version=opaque.parse_contract_version,
    )
    html_attempt = _Attempt(outcome="SUCCEEDED", document_id=DOCUMENT_ID)
    session = _FakeSession(
        task=_Task(),
        entities={InvestigationDocumentExclusion: [[_exclusion()]]},
        scalars=[legacy_attempt, 1, 1, html_attempt, 2, 2],
    )

    result = describe_documents(cast(Any, session), materials)

    assert result["status"] == "PREPARED"
    assert result["excluded_count"] == 1 and result["unsupported_count"] == 0
    legacy = result["materials"][0]
    assert legacy["excluded"] is True
    assert legacy["evidence_mode"] == "OPAQUE_NO_TEXT"
    assert legacy["parser_name"] == opaque.name
    assert legacy["parse_contract_version"] == P9B_BLOCK_PARSE_CONTRACT_VERSION
    assert legacy["outcome"] == "SUCCEEDED" and legacy["block_count"] == 1
    assert legacy["exclusion"] == {
        "reason": REASON,
        "excluded_by": str(REVIEWER_ID),
        "excluded_at": "2026-09-11T09:00:00+00:00",
    }
    assert result["materials"][1] == _html_row()


def test_excluded_material_without_an_opaque_block_has_no_evidence_mode() -> None:
    """An exclusion alone is not evidence; ``prepare_documents`` still has to run."""
    materials = [_material("legacy.doc", LEGACY_MEDIA_TYPE), _material("notice", HTML_MEDIA_TYPE)]
    # The excluded row is described by the opaque parser, so it consumes the first
    # ParseAttempt lookup and reports "not parsed yet" when there is none.
    session = _FakeSession(
        task=_Task(),
        entities={InvestigationDocumentExclusion: [[_exclusion()]]},
        scalars=[None, _Attempt(outcome="SUCCEEDED", document_id=DOCUMENT_ID), 2, 2],
    )

    result = describe_documents(cast(Any, session), materials)
    legacy = result["materials"][0]

    assert legacy["excluded"] is True and legacy["evidence_mode"] is None
    assert legacy["outcome"] == "NOT_PREPARED" and legacy["error_code"] is None
    assert legacy["exclusion"]["reason"] == REASON
    assert result["status"] == "NEEDS_ATTENTION" and result["excluded_count"] == 1


def test_revoked_exclusion_stops_applying() -> None:
    materials = [_material("legacy.doc", LEGACY_MEDIA_TYPE)]
    revoked = _exclusion(
        revoked_at=datetime(2026, 9, 11, 10, 0, tzinfo=UTC),
        revoked_by=REVIEWER_ID,
        revoked_reason="previously withdrawn",
    )
    session = _FakeSession(task=_Task(), entities={InvestigationDocumentExclusion: [[revoked]]})

    result = describe_documents(cast(Any, session), materials)

    assert result["materials"][0] == _legacy_row_unsupported()
    assert result["excluded_count"] == 0 and result["unsupported_count"] == 1


def _exclusion_session(
    task: _Task,
    outcome_before: str,
    *,
    existing: list[Any] | None = None,
) -> _FakeSession:
    """Session for ``exclude_document`` with ``legacy.doc`` in state ``outcome_before``."""
    media_type = LEGACY_MEDIA_TYPE if outcome_before == "UNSUPPORTED" else PDF_MEDIA_TYPE
    material = _material("legacy.doc", media_type)
    if outcome_before == "UNSUPPORTED":
        # No parser at all, so describe_documents issues no query for that row.
        scalars: list[Any] = []
    elif outcome_before == "NOT_PREPARED":
        scalars = [None]
    else:
        scalars = [_Attempt(outcome=outcome_before, error_code="READER_NO_TEXT")]
    return _FakeSession(
        task=task,
        account=_Account(),
        raw=_Raw(),
        entities={
            InvestigationMaterial: [[material]],
            InvestigationDocumentExclusion: [existing or []],
        },
        scalars=scalars,
    )


def _exclude(store: _FakeStore, reason: str = REASON) -> dict[str, Any]:
    return exclude_document(
        cast(InvestigationStore, store),
        TASK_ID,
        DELIVERY_HASH,
        "legacy.doc",
        reason,
        _principal(),
    )


def _revoke(store: _FakeStore, reason: str = REVOCATION) -> dict[str, Any]:
    return revoke_exclusion(
        cast(InvestigationStore, store),
        TASK_ID,
        DELIVERY_HASH,
        "legacy.doc",
        reason,
        _principal(),
    )


def test_exclusion_is_recorded_with_frozen_provenance() -> None:
    task = _Task()
    session = _exclusion_session(task, "UNSUPPORTED")
    store = _FakeStore(session, task)

    view = _exclude(store, f"  {REASON}  ")

    row = session.added[0]
    assert isinstance(row, InvestigationDocumentExclusion)
    assert row.reason == REASON  # trimmed, not the raw submission
    assert (row.task_id, row.material_id, row.delivery_hash) == (
        TASK_ID,
        "legacy.doc",
        DELIVERY_HASH,
    )
    assert row.raw_artifact_id == ARTIFACT_ID and row.media_type == LEGACY_MEDIA_TYPE
    assert row.excluded_by == REVIEWER_ID and row.revoked_at is None
    assert view == {"task_id": str(TASK_ID), "status": "PENDING_REVIEW"}


@pytest.mark.parametrize(
    "status", ["COLLECTING", "REJECTED", "EXECUTION_UNCERTAIN", "INVESTIGATING", "EXPIRED"]
)
def test_exclusion_is_rejected_outside_reviewable_statuses(status: str) -> None:
    task = _Task(status=status)
    session = _exclusion_session(task, "UNSUPPORTED")
    store = _FakeStore(session, task)

    with pytest.raises(InvestigationError, match="DOCUMENT_EXCLUSION_NOT_ALLOWED"):
        _exclude(store)
    assert session.added == []


def test_exclusion_is_rejected_for_a_superseded_delivery() -> None:
    task = _Task()
    session = _exclusion_session(task, "UNSUPPORTED")
    store = _FakeStore(session, task)

    with pytest.raises(InvestigationError, match="DOCUMENT_EXCLUSION_DELIVERY_CONFLICT"):
        exclude_document(
            cast(InvestigationStore, store),
            TASK_ID,
            "b" * 64,
            "legacy.doc",
            REASON,
            _principal(),
        )
    assert session.added == []


@pytest.mark.parametrize("outcome", ["NOT_PREPARED", "SUCCEEDED", "FAILED", "NEEDS_REVIEW"])
def test_exclusion_is_rejected_for_anything_but_unsupported(outcome: str) -> None:
    """Otherwise exclusion would become a back door for hiding parse failures."""
    task = _Task()
    session = _exclusion_session(task, outcome)
    store = _FakeStore(session, task)

    with pytest.raises(InvestigationError, match="DOCUMENT_EXCLUSION_NOT_UNSUPPORTED"):
        _exclude(store)
    assert session.added == []


@pytest.mark.parametrize("reason", ["", "   ", "short", "1234567"])
def test_exclusion_is_rejected_without_a_meaningful_reason(reason: str) -> None:
    task = _Task()
    session = _exclusion_session(task, "UNSUPPORTED")
    store = _FakeStore(session, task)

    with pytest.raises(InvestigationError, match="DOCUMENT_EXCLUSION_REASON_REQUIRED"):
        _exclude(store, reason)
    assert session.added == []


def test_exclusion_is_rejected_when_the_reason_exceeds_the_column() -> None:
    task = _Task()
    session = _exclusion_session(task, "UNSUPPORTED")
    store = _FakeStore(session, task)

    with pytest.raises(InvestigationError, match="DOCUMENT_EXCLUSION_REASON_REQUIRED"):
        _exclude(store, "x" * 2001)
    assert session.added == []


def test_duplicate_exclusion_is_rejected() -> None:
    task = _Task()
    session = _exclusion_session(task, "UNSUPPORTED", existing=[_exclusion()])
    store = _FakeStore(session, task)

    with pytest.raises(InvestigationError, match="DOCUMENT_EXCLUSION_ALREADY_PRESENT"):
        _exclude(store)
    assert session.added == []


def test_exclusion_is_rejected_for_a_material_outside_the_task() -> None:
    task = _Task()
    session = _exclusion_session(task, "UNSUPPORTED")
    store = _FakeStore(session, task)

    with pytest.raises(InvestigationError, match="DOCUMENT_EXCLUSION_MATERIAL_NOT_FOUND"):
        exclude_document(
            cast(InvestigationStore, store),
            TASK_ID,
            DELIVERY_HASH,
            "missing.doc",
            REASON,
            _principal(),
        )
    assert session.added == []


def test_exclusion_requires_the_operator_role() -> None:
    task = _Task()
    session = _exclusion_session(task, "UNSUPPORTED")
    store = _FakeStore(session, task)

    with pytest.raises(ReviewerAuthenticationError):
        exclude_document(
            cast(InvestigationStore, store),
            TASK_ID,
            DELIVERY_HASH,
            "legacy.doc",
            REASON,
            _principal(frozenset({ReviewerRole.VALIDATION_REVIEWER})),
        )
    assert session.added == []


def test_exclusion_requires_an_active_account() -> None:
    task = _Task()
    session = _exclusion_session(task, "UNSUPPORTED")
    session.resolve(ReviewerAccountModel, _Account(active=False))
    store = _FakeStore(session, task)

    with pytest.raises(InvestigationError, match="DOCUMENT_OPERATOR_REQUIRED"):
        _exclude(store)
    assert session.added == []


def test_revocation_records_actor_reason_and_keeps_history() -> None:
    task = _Task()
    row = _exclusion()
    session = _FakeSession(
        task=task, account=_Account(), entities={InvestigationDocumentExclusion: [[row]]}
    )
    store = _FakeStore(session, task)

    _revoke(store)

    assert row.revoked_at == datetime(2026, 9, 11, 12, 0, tzinfo=UTC)
    assert row.revoked_by == REVIEWER_ID
    assert row.revoked_reason == REVOCATION
    assert row.excluded_by == REVIEWER_ID  # who excluded it survives the revocation


def test_revocation_is_rejected_without_an_effective_exclusion() -> None:
    task = _Task()
    session = _FakeSession(
        task=task, account=_Account(), entities={InvestigationDocumentExclusion: [[]]}
    )
    store = _FakeStore(session, task)

    with pytest.raises(InvestigationError, match="DOCUMENT_EXCLUSION_NOT_FOUND"):
        _revoke(store)


def test_revoking_an_already_revoked_exclusion_is_rejected() -> None:
    task = _Task()
    revoked = _exclusion(
        revoked_at=datetime(2026, 9, 11, 10, 0, tzinfo=UTC),
        revoked_by=REVIEWER_ID,
        revoked_reason="previously withdrawn",
    )
    session = _FakeSession(
        task=task, account=_Account(), entities={InvestigationDocumentExclusion: [[revoked]]}
    )
    store = _FakeStore(session, task)

    with pytest.raises(InvestigationError, match="DOCUMENT_EXCLUSION_NOT_FOUND"):
        _revoke(store)
    assert revoked.revoked_reason == "previously withdrawn"  # untouched


def test_revocation_checks_status_and_delivery() -> None:
    task = _Task(status="REJECTED")
    session = _FakeSession(
        task=task, account=_Account(), entities={InvestigationDocumentExclusion: [[_exclusion()]]}
    )
    store = _FakeStore(session, task)

    with pytest.raises(InvestigationError, match="DOCUMENT_EXCLUSION_NOT_ALLOWED"):
        _revoke(store)


def test_revocation_is_rejected_without_a_meaningful_reason() -> None:
    task = _Task()
    row = _exclusion()
    session = _FakeSession(
        task=task, account=_Account(), entities={InvestigationDocumentExclusion: [[row]]}
    )
    store = _FakeStore(session, task)

    with pytest.raises(InvestigationError, match="DOCUMENT_EXCLUSION_REASON_REQUIRED"):
        _revoke(store, "short")
    assert row.revoked_at is None

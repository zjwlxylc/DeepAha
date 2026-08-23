import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from deepaha.acquisition.contracts import (
    ContentExpectations,
    DiscoveryKind,
    DiscoverySpec,
    ExpectedChangeFrequency,
    FetchPlanStep,
    FetchStrategy,
    HealthThresholds,
    SourceRecipe,
    SourceUsageRole,
    ValidationStatus,
)
from deepaha.acquisition.replay import (
    ControlledDirectoryStore,
    ReplayBinding,
    ReplayCorpusEntry,
    ReplayCorpusManifest,
    ReplayExpectedOutcome,
    ReplayRunner,
    ReplayStatus,
    load_replay_manifest,
)
from deepaha.acquisition.validation import ContentValidator
from deepaha.documents.html import LxmlHtmlParser

SOURCE_ID = UUID("0198d239-4b00-7000-8000-000000000212")
ENDPOINT_ID = UUID("0198d239-4b00-7000-8000-000000000213")
ARTIFACT_ID = UUID("01a02dd1-8a8b-72fa-8447-f7e54ffaf24f")
RECIPE_ID = UUID("01a02f3c-49d1-715f-9173-a40b388d6747")
ENTRY_ID = UUID("01a02f3c-49d1-715f-9173-a40cf29a02f4")
BODY = b'<html><body><ul><li><a href="/detail/1.html">One</a></li></ul></body></html>'
BODY_SHA256 = sha256(BODY).hexdigest()


class MemoryStore:
    def __init__(self, values: dict[str, bytes]) -> None:
        self.values = values
        self.requests: list[str] = []

    def get_bytes(self, *, key: str) -> bytes:
        self.requests.append(key)
        return self.values[key]


def recipe() -> SourceRecipe:
    return SourceRecipe(
        recipe_id=RECIPE_ID,
        source_id=SOURCE_ID,
        endpoint_id=ENDPOINT_ID,
        endpoint_policy_version="2026-08-21.1",
        recipe_version="1.0.0",
        usage_role=SourceUsageRole.PRIMARY_EVIDENCE,
        allowed_hosts=("www.mohrss.gov.cn",),
        expected_media_types=("text/html",),
        allowed_url_patterns=("/*",),
        fetch_plan=(FetchPlanStep(strategy=FetchStrategy.STATIC_HTTP, fallback_on=()),),
        expectations=ContentExpectations(
            minimum_bytes=1,
            maximum_bytes=10_000,
            required_markers=("One",),
            forbidden_markers=(),
            required_selectors=("ul li",),
            minimum_discovered_count=1,
            structured_kind=None,
            contract_version="1.0.0",
        ),
        discovery=DiscoverySpec(
            kind=DiscoveryKind.HTML_LINKS,
            item_selector="ul li",
            detail_link_selector="a",
            attachment_link_selector=None,
            pagination_link_selector=None,
            structured_items_path=(),
            detail_limit=5,
            attachment_limit=0,
            pagination_limit=0,
        ),
        maximum_requests=2,
        maximum_elapsed_seconds=30,
        health=HealthThresholds(
            expected_change_frequency=ExpectedChangeFrequency.DAILY,
            zero_discovery_grace_runs=1,
            consecutive_failure_limit=2,
            selector_drift_grace_runs=1,
        ),
        active=True,
        verified_at=datetime(2026, 8, 23, 8, tzinfo=UTC),
        contract_version="1.0.0",
    )


def entry(**overrides: object) -> ReplayCorpusEntry:
    values: dict[str, object] = {
        "entry_id": ENTRY_ID,
        "source_id": SOURCE_ID,
        "endpoint_id": ENDPOINT_ID,
        "artifact_id": ARTIFACT_ID,
        "recipe_id": RECIPE_ID,
        "endpoint_policy_version": "2026-08-21.1",
        "recipe_version": "1.0.0",
        "original_url": "https://www.mohrss.gov.cn/list/",
        "final_url": "https://www.mohrss.gov.cn/list/",
        "fetched_at": "2026-08-23T08:00:00Z",
        "http_status": 200,
        "media_type": "text/html",
        "content_sha256": BODY_SHA256,
        "byte_size": len(BODY),
        "object_key": f"raw/sha256/{BODY_SHA256[:2]}/{BODY_SHA256}",
        "strategy": "STATIC_HTTP",
        "fetcher_name": "deepaha-static-http",
        "fetcher_version": "1.0.0",
        "validator_name": "deepaha-content-validator",
        "validator_version": "1.0.0",
        "parser_name": "html_lxml",
        "parser_version": "0.2.0",
        "expected": ReplayExpectedOutcome.model_validate(
            {
                "validation_status": ValidationStatus.VALID,
                "diagnostic_codes": (),
                "discovered_urls": ("https://www.mohrss.gov.cn/detail/1.html",),
                "parse_outcome": "SUCCEEDED",
                "parse_error_code": None,
                "normalized_text_sha256": (
                    "82a5f8bf6ec19baad113b7f1744ba4163b6efbcbd73e79d9d98f129c63688c44"
                ),
                "evidence_locator_count": 1,
            }
        ),
        "contract_version": "1.0.0",
    }
    values.update(overrides)
    return ReplayCorpusEntry.model_validate(values)


def runner(store: MemoryStore) -> ReplayRunner:
    return ReplayRunner(
        object_store=store,
        validator=ContentValidator(),
        parsers=(LxmlHtmlParser(),),
        fetcher_versions={"deepaha-static-http": "1.0.0"},
    )


def binding(**overrides: UUID) -> ReplayBinding:
    values = {
        "source_id": SOURCE_ID,
        "endpoint_id": ENDPOINT_ID,
        "artifact_id": ARTIFACT_ID,
    }
    values.update(overrides)
    return ReplayBinding(**values)


def test_manifest_is_strict_and_forbids_embedded_body(tmp_path: Path) -> None:
    embedded_entry = entry().model_dump(mode="json")
    embedded_entry["body"] = BODY.decode()
    payload = {
        "schema_version": "1.0.0",
        "corpus_name": "test-real-corpus",
        "entries": [embedded_entry],
    }
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError, match="body"):
        load_replay_manifest(path)


def test_manifest_rejects_duplicate_entry_or_artifact_identity() -> None:
    with pytest.raises(ValidationError, match="duplicate replay entry or artifact identity"):
        ReplayCorpusManifest(
            schema_version="1.0.0",
            corpus_name="test-real-corpus",
            entries=(entry(), entry()),
        )


def test_controlled_directory_store_rejects_escape_and_missing_object(tmp_path: Path) -> None:
    store = ControlledDirectoryStore(tmp_path)

    with pytest.raises(ValueError, match="relative controlled object key"):
        store.get_bytes(key="../secret.txt")
    with pytest.raises(FileNotFoundError):
        store.get_bytes(key="raw/missing.html")


def test_missing_controlled_object_is_explicitly_blocked() -> None:
    store = MemoryStore({})

    result = runner(store).run(entry=entry(), recipe=recipe(), binding=binding())

    assert result.status is ReplayStatus.BLOCKED
    assert result.error_code == "REPLAY_OBJECT_MISSING"
    assert result.validation_status is None


@pytest.mark.parametrize(
    ("changed", "error_code"),
    [
        ({"content_sha256": "0" * 64}, "REPLAY_OBJECT_HASH_MISMATCH"),
        ({"byte_size": len(BODY) + 1}, "REPLAY_OBJECT_SIZE_MISMATCH"),
        ({"fetcher_version": "9.9.9"}, "REPLAY_FETCHER_VERSION_MISMATCH"),
        ({"validator_version": "9.9.9"}, "REPLAY_VALIDATOR_VERSION_MISMATCH"),
        ({"parser_version": "9.9.9"}, "REPLAY_PARSER_VERSION_MISMATCH"),
    ],
)
def test_integrity_and_runtime_version_mismatch_fail_closed(
    changed: dict[str, object], error_code: str
) -> None:
    store = MemoryStore({entry().object_key: BODY})

    result = runner(store).run(entry=entry(**changed), recipe=recipe(), binding=binding())

    assert result.status is ReplayStatus.FAILED
    assert result.error_code == error_code


@pytest.mark.parametrize(
    "wrong_binding",
    [
        ReplayBinding(UUID("0198d239-4b00-7000-8000-000000000214"), ENDPOINT_ID, ARTIFACT_ID),
        ReplayBinding(SOURCE_ID, UUID("0198d239-4b00-7000-8000-000000000215"), ARTIFACT_ID),
        ReplayBinding(SOURCE_ID, ENDPOINT_ID, UUID("01a02dd1-8a8b-72fa-8447-f7e54ffaf250")),
    ],
)
def test_wrong_source_endpoint_or_artifact_binding_fails(wrong_binding: ReplayBinding) -> None:
    store = MemoryStore({entry().object_key: BODY})

    result = runner(store).run(entry=entry(), recipe=recipe(), binding=wrong_binding)

    assert result.status is ReplayStatus.FAILED
    assert result.error_code == "REPLAY_BINDING_MISMATCH"


def test_valid_replay_matches_expected_discovery_and_parse_deterministically() -> None:
    store = MemoryStore({entry().object_key: BODY})
    replay_runner = runner(store)

    first = replay_runner.run(entry=entry(), recipe=recipe(), binding=binding())
    second = replay_runner.run(entry=entry(), recipe=recipe(), binding=binding())

    assert first == second
    assert first.status is ReplayStatus.PASSED
    assert first.validation_status is ValidationStatus.VALID
    assert first.discovered_urls == ("https://www.mohrss.gov.cn/detail/1.html",)
    assert first.parse_outcome == "SUCCEEDED"
    assert first.evidence_locator_count == 1
    assert len(first.result_sha256 or "") == 64
    assert store.requests == [entry().object_key, entry().object_key]


def test_expected_outcome_drift_fails_closed() -> None:
    changed_expected = entry().expected.model_copy(
        update={"discovered_urls": ("https://www.mohrss.gov.cn/detail/changed.html",)},
    )
    changed = entry(expected=changed_expected)
    store = MemoryStore({changed.object_key: BODY})

    result = runner(store).run(entry=changed, recipe=recipe(), binding=binding())

    assert result.status is ReplayStatus.FAILED
    assert result.error_code == "REPLAY_EXPECTATION_MISMATCH"

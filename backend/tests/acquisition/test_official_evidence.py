from datetime import UTC, datetime
from uuid import UUID

import pytest
from pydantic import ValidationError

from deepaha.acquisition import OfficialEvidenceTask as PublicOfficialEvidenceTask
from deepaha.acquisition.contracts import DiscoveryKind, FetchStrategy, SourceRecipe
from deepaha.acquisition.official_evidence import (
    OfficialEvidencePolicyError,
    OfficialEvidenceRequest,
    OfficialEvidenceTask,
    request_payload_sha256,
    validate_official_evidence_policy,
)
from deepaha.sources.models import Source, SourceEndpoint

NOW = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


def test_task_is_exposed_as_the_acquisition_entrypoint() -> None:
    assert PublicOfficialEvidenceTask is OfficialEvidenceTask


def request(*, request_key: str = "official-request:2026-09-01:1") -> OfficialEvidenceRequest:
    return OfficialEvidenceRequest.model_validate(
        {
            "request_key": request_key,
            "source_id": "019c0000-0000-7000-8000-000000000101",
            "endpoint_id": "019c0000-0000-7000-8000-000000000102",
            "recipe_id": "019c0000-0000-7000-8000-000000000103",
            "requested_url": "https://official.example/notices/1",
            "contract_version": "1.0.0",
        }
    )


def source_and_endpoint() -> tuple[Source, SourceEndpoint]:
    source_id = UUID("019c0000-0000-7000-8000-000000000101")
    endpoint_id = UUID("019c0000-0000-7000-8000-000000000102")
    source = Source(
        source_id=source_id,
        public_id=f"src_{source_id.hex}",
        canonical_url="https://official.example/",
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
        max_attempts=2,
        robots_url="https://official.example/robots.txt",
        robots_decision="ALLOWED",
        robots_checked_at=NOW,
        content_use_basis="OFFICIAL_PUBLIC_ACCESS",
        license_name=None,
        license_url=None,
        attribution="Synthetic official authority",
        fixture_storage_allowed=False,
        usage_note="Synthetic unit fixture.",
        policy_version="2026-09-01.1",
        active=True,
        verified_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )
    return source, endpoint


def recipe() -> SourceRecipe:
    return SourceRecipe.model_validate(
        {
            "recipe_id": "019c0000-0000-7000-8000-000000000103",
            "source_id": "019c0000-0000-7000-8000-000000000101",
            "endpoint_id": "019c0000-0000-7000-8000-000000000102",
            "endpoint_policy_version": "2026-09-01.1",
            "recipe_version": "2026-09-01.1",
            "usage_role": "PRIMARY_EVIDENCE",
            "allowed_hosts": ["official.example"],
            "expected_media_types": ["text/html"],
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


def test_payload_hash_is_canonical_and_excludes_idempotency_key() -> None:
    first = request(request_key="client-a:request-1")
    replay = request(request_key="client-b:request-9")

    assert request_payload_sha256(first) == request_payload_sha256(replay)
    assert len(request_payload_sha256(first)) == 64
    assert isinstance(first.source_id, UUID)


@pytest.mark.parametrize(
    "request_key",
    ("", "spaces are forbidden", "slash/is/forbidden", "x" * 129),
)
def test_request_key_is_bounded_and_safe(request_key: str) -> None:
    with pytest.raises(ValidationError):
        request(request_key=request_key)


def test_policy_accepts_only_single_static_official_primary_request() -> None:
    source, endpoint = source_and_endpoint()

    validate_official_evidence_policy(request(), source, endpoint, recipe())


@pytest.mark.parametrize(
    ("source_update", "endpoint_update", "recipe_update"),
    (
        ({"tier": "TRUSTED_SECONDARY"}, {}, {}),
        ({"active": False}, {}, {}),
        ({}, {"robots_decision": "UNKNOWN"}, {}),
        ({}, {"content_use_basis": "UNKNOWN"}, {}),
        ({}, {"browser_policy": "FALLBACK"}, {}),
        ({}, {}, {"usage_role": "OFFICIAL_DISCOVERY"}),
        ({}, {}, {"maximum_requests": 2}),
    ),
)
def test_policy_rejects_non_official_or_non_minimal_request(
    source_update: dict[str, object],
    endpoint_update: dict[str, object],
    recipe_update: dict[str, object],
) -> None:
    source, endpoint = source_and_endpoint()
    for name, value in source_update.items():
        setattr(source, name, value)
    for name, value in endpoint_update.items():
        setattr(endpoint, name, value)
    candidate = recipe().model_copy(update=recipe_update)

    with pytest.raises(OfficialEvidencePolicyError, match="OFFICIAL_EVIDENCE_POLICY_REJECTED"):
        validate_official_evidence_policy(request(), source, endpoint, candidate)


def test_policy_rejects_request_url_outside_recipe_path() -> None:
    source, endpoint = source_and_endpoint()
    outside = request().model_copy(update={"requested_url": "https://official.example/private/1"})

    with pytest.raises(OfficialEvidencePolicyError, match="OFFICIAL_EVIDENCE_POLICY_REJECTED"):
        validate_official_evidence_policy(outside, source, endpoint, recipe())


def test_policy_rejects_browser_and_discovery_plans() -> None:
    source, endpoint = source_and_endpoint()
    configured = recipe()
    browser = configured.model_copy(
        update={
            "fetch_plan": (
                configured.fetch_plan[0].model_copy(update={"strategy": FetchStrategy.BROWSER}),
            )
        }
    )
    discovery = configured.model_copy(
        update={
            "discovery": configured.discovery.model_copy(
                update={
                    "kind": DiscoveryKind.HTML_LINKS,
                    "item_selector": "main",
                    "detail_link_selector": "a.notice",
                    "detail_limit": 1,
                }
            )
        }
    )

    for candidate in (browser, discovery):
        with pytest.raises(OfficialEvidencePolicyError):
            validate_official_evidence_policy(request(), source, endpoint, candidate)

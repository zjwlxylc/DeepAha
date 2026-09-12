from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import pytest
from fastapi import Response
from sqlalchemy import func, select

from deepaha.api.investigations import list_sources
from deepaha.contracts.phase1 import OpportunityStatus, SourceTier
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.contracts.phase3 import OpportunityDocumentRole, ResolutionDisposition
from deepaha.investigations.contracts import CreateInvestigation, InvestigationError
from deepaha.opportunities.resolver import resolve_document
from deepaha.opportunities.types import OpportunityPatch, ResolutionDocument, ResolutionIndex
from deepaha.sources.models import SourceEndpoint
from deepaha.sources.registry import import_registry, load_registry_manifest
from tests.integration import test_investigation_store as support
from tests.integration.test_investigation_store import StoreHarness

harness = support.harness
pytestmark = pytest.mark.integration

SOURCES_ROOT = Path(__file__).parents[3] / "config" / "sources"
PRIMARY_AUTHORITY = "浙江省人力资源和社会保障厅"
PRIMARY_NOTICE_URL = (
    "https://rlsbt.zj.gov.cn/col/col1229743683/art/2026/art_99f2702a91aa43edaab3ef5037d8d0ad.html"
)


def _attachment_name(url: str) -> str:
    """Return the decoded ``fileName`` of an rlsbt document-download URL."""
    name = parse_qs(urlsplit(url).query)["fileName"][0]
    return name


def _seed_registry(store_harness: StoreHarness) -> None:
    """Import the real phase2 + direct-wma manifests twice to prove idempotent init."""
    for _ in range(2):
        with store_harness.factory.begin() as session:
            import_registry(
                session, load_registry_manifest(SOURCES_ROOT / "phase2-official-endpoints.json")
            )
            import_registry(session, load_registry_manifest(SOURCES_ROOT / "direct-wma-local.json"))


def test_real_initializer_adds_exact_user_approved_samples_without_upgrading_old_sources(
    harness: StoreHarness,
) -> None:
    _seed_registry(harness)
    sources = list_sources(harness.store, harness.principal, Response())["sources"]
    samples = [row for row in sources if "www.zjhr.com" in row["allowed_hosts"]]
    assert len(samples) == 4
    with harness.factory() as session:
        assert (
            session.scalar(
                select(func.count())
                .select_from(SourceEndpoint)
                .where(SourceEndpoint.content_use_basis == "LINK_ONLY")
            )
            == 26
        )
    command = CreateInvestigation(
        source_id=samples[0]["source_id"],
        endpoint_id=samples[0]["endpoint_id"],
        notice_url=samples[0]["url"],
        brief="Synthetic registration only; no remote call.",
        calibration=True,
    )
    task_id = harness.store.create(command, harness.principal, "approved-sample")
    assert harness.store.get(task_id)["source_snapshot"]["tier"] == "OFFICIAL_AGGREGATOR"
    with pytest.raises(InvestigationError, match="APPROVED_SOURCE_REQUIRED"):
        harness.store.create(
            command.model_copy(update={"notice_url": "https://www.zjhr.com/unreviewed"}),
            harness.principal,
            "unreviewed-url",
        )


def test_first_hand_primary_source_is_listed_and_admitted_as_primary(
    harness: StoreHarness,
) -> None:
    _seed_registry(harness)
    sources = list_sources(harness.store, harness.principal, Response())["sources"]
    primary = [row for row in sources if row["authority_name"] == PRIMARY_AUTHORITY]
    assert len(primary) == 1
    row = primary[0]
    assert row["allowed_hosts"] == ["rlsbt.zj.gov.cn"]
    assert row["url"] == PRIMARY_NOTICE_URL
    # The sample must carry the notice body plus the two long query-string attachments.
    expected_artifacts = tuple(row["sample"]["expected_artifact_urls"])
    assert expected_artifacts[0] == PRIMARY_NOTICE_URL
    assert (
        _attachment_name(expected_artifacts[1])
        == "浙江省省属事业单位2026下半年集中公开招聘计划表.xlsx"
    )
    assert _attachment_name(expected_artifacts[2]) == "应聘指南.doc"

    command = CreateInvestigation(
        source_id=row["source_id"],
        endpoint_id=row["endpoint_id"],
        notice_url=row["url"],
        brief="Synthetic registration only; no remote call.",
        expected_artifact_urls=expected_artifacts,
        calibration=True,
    )
    task_id = harness.store.create(command, harness.principal, "primary-approved-sample")
    snapshot = harness.store.get(task_id)["source_snapshot"]
    assert snapshot["tier"] == "OFFICIAL_PRIMARY"
    assert snapshot["authority_name"] == PRIMARY_AUTHORITY
    assert snapshot["content_use_basis"] == "OFFICIAL_PUBLIC_ACCESS"


def test_local_manifest_declares_four_aggregator_and_one_primary_endpoint() -> None:
    manifest = load_registry_manifest(SOURCES_ROOT / "direct-wma-local.json")
    endpoints_by_tier = {entry.source.tier: entry.endpoints for entry in manifest.sources}
    assert len(manifest.sources) == 2
    assert len(endpoints_by_tier[SourceTier.OFFICIAL_AGGREGATOR]) == 4
    assert len(endpoints_by_tier[SourceTier.OFFICIAL_PRIMARY]) == 1
    endpoints = [endpoint for entry in manifest.sources for endpoint in entry.endpoints]
    assert len(endpoints) == 5
    assert all(endpoint.content_use_basis == "OFFICIAL_PUBLIC_ACCESS" for endpoint in endpoints)
    assert all(endpoint.robots_decision == "NOT_APPLICABLE" for endpoint in endpoints)
    assert {endpoint.policy_version for endpoint in endpoints} == {
        "2026-09-11.direct-wma-zjhr.1",
        "2026-09-11.direct-wma-rlsbt.1",
    }


def test_primary_creates_while_aggregator_still_requires_review(
    harness: StoreHarness,
) -> None:
    """Regression nail: the registered first-hand source can register identity; the
    aggregator must keep hitting NEEDS_REVIEW / AGGREGATOR_REQUIRES_REVIEW."""
    _seed_registry(harness)
    manifest = load_registry_manifest(SOURCES_ROOT / "direct-wma-local.json")
    primary_source = next(
        entry.source
        for entry in manifest.sources
        if entry.source.tier is SourceTier.OFFICIAL_PRIMARY
    )
    aggregator_source = next(
        entry.source
        for entry in manifest.sources
        if entry.source.tier is SourceTier.OFFICIAL_AGGREGATOR
    )

    def document(source_id: UUID, source_tier: SourceTier) -> ResolutionDocument:
        return ResolutionDocument(
            document_id=uuid4(),
            source_id=source_id,
            source_tier=source_tier,
            evidence_ref_id=uuid4(),
            role=OpportunityDocumentRole.PRIMARY_NOTICE,
            canonical_url=PRIMARY_NOTICE_URL,
            external_id=None,
            references_document_ids=(),
            effective_at=datetime(2026, 9, 11, 4, tzinfo=UTC),
            facts=OpportunityPatch(
                canonical_title="浙江省省属事业单位2026年下半年集中公开招聘人员公告",
                type=OpportunityTypeV02.PUBLIC_INSTITUTION_JOB,
                issuer_name=PRIMARY_AUTHORITY,
                status=OpportunityStatus.UNKNOWN,
            ),
        )

    primary_decision = resolve_document(
        document(primary_source.source_id, primary_source.tier), ResolutionIndex.empty()
    )
    assert primary_decision.disposition is ResolutionDisposition.CREATED
    assert primary_decision.opportunity_id is None

    aggregator_decision = resolve_document(
        document(aggregator_source.source_id, aggregator_source.tier), ResolutionIndex.empty()
    )
    assert aggregator_decision.disposition is ResolutionDisposition.NEEDS_REVIEW
    assert aggregator_decision.opportunity_id is None
    assert aggregator_decision.reason_codes == ("AGGREGATOR_REQUIRES_REVIEW",)

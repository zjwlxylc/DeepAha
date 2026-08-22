from datetime import date, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from deepaha.contracts.phase1 import OpportunityStatus
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.opportunities.models import Opportunity
from deepaha.public_catalog.schemas import (
    PersonalizationAvailability,
    PublicDataLabel,
    PublicOpportunityQuery,
    PublicOpportunitySort,
)
from deepaha.public_catalog.service import PublicCatalogService
from tests.public_catalog.seed_phase5_browser import assert_phase5_browser_database_url
from tests.public_catalog.support import persist_phase5_fixture, stable_uuid7

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "candidate_url",
    [
        "postgresql+psycopg://deepaha:test@127.0.0.1:55432/deepaha",
        "postgresql+psycopg://deepaha:test@127.0.0.1:55434/deepaha",
        "postgresql+psycopg://deepaha:test@localhost:55435/deepaha",
        "postgresql+psycopg://deepaha:test@127.0.0.1:55435/other",
    ],
)
def test_browser_seed_refuses_non_phase5_database(candidate_url: str) -> None:
    with pytest.raises(ValueError, match="127.0.0.1:55435/deepaha"):
        assert_phase5_browser_database_url(candidate_url)


def test_browser_seed_accepts_only_exact_phase5_database() -> None:
    assert_phase5_browser_database_url("postgresql+psycopg://deepaha:test@127.0.0.1:55435/deepaha")


def test_list_projects_complete_governed_cards_in_published_order(session: Session) -> None:
    public_ids = persist_phase5_fixture(session)
    service = PublicCatalogService(session)

    page = service.list_opportunities(PublicOpportunityQuery())

    assert [item.public_id for item in page.items] == list(public_ids)
    assert page.count == 3
    assert page.next_cursor is None
    assert page.data_labels == (PublicDataLabel.LICENSE_SAFE_FIXTURE,)
    assert page.reproduced_at == datetime.fromisoformat("2026-08-22T03:00:00+00:00")
    assert all(item.title and item.issuer_name and item.jurisdiction for item in page.items)
    assert all(item.published_at and item.deadline and item.last_verified_at for item in page.items)
    assert all(item.data_label is PublicDataLabel.LICENSE_SAFE_FIXTURE for item in page.items)
    assert page.items[1].change_markers == ("DEADLINE_CHANGED",)


def test_search_filters_and_deadline_sort_are_literal_and_finite(session: Session) -> None:
    persist_phase5_fixture(session)
    service = PublicCatalogService(session)

    assert service.list_opportunities(PublicOpportunityQuery(q="%_")).count == 1
    assert service.list_opportunities(PublicOpportunityQuery(q="_测试")).count == 1
    assert service.list_opportunities(PublicOpportunityQuery(q="opp_")).count == 3
    assert (
        service.list_opportunities(PublicOpportunityQuery(type=OpportunityTypeV02.SCHOLARSHIP))
        .items[0]
        .title
        == "合成科研奖学金 %_ 字面量专项"
    )
    assert (
        service.list_opportunities(PublicOpportunityQuery(status=OpportunityStatus.OPEN)).count == 1
    )
    assert service.list_opportunities(PublicOpportunityQuery(region="合成宁波市")).count == 1

    deadline_page = service.list_opportunities(
        PublicOpportunityQuery(sort=PublicOpportunitySort.DEADLINE_ASC)
    )
    assert [item.deadline for item in deadline_page.items] == [
        date(2026, 8, 31),
        date(2026, 9, 12),
        date(2026, 9, 20),
    ]


def test_cursor_pagination_has_no_duplicate_or_skip(session: Session) -> None:
    persist_phase5_fixture(session)
    service = PublicCatalogService(session)

    first = service.list_opportunities(PublicOpportunityQuery(limit=1))
    assert first.next_cursor is not None
    second = service.list_opportunities(PublicOpportunityQuery(limit=1, cursor=first.next_cursor))
    assert second.next_cursor is not None
    third = service.list_opportunities(PublicOpportunityQuery(limit=1, cursor=second.next_cursor))

    ids = [first.items[0].public_id, second.items[0].public_id, third.items[0].public_id]
    assert len(set(ids)) == 3
    assert third.next_cursor is None


@pytest.mark.parametrize("failure_mode", ["internal", "stale", "incomplete", "non_official"])
def test_visibility_excludes_unapproved_or_incomplete_rows(
    session: Session,
    failure_mode: str,
) -> None:
    public_ids = persist_phase5_fixture(session)
    alpha_id = stable_uuid7("alpha:opportunity")
    if failure_mode == "internal":
        opportunity = session.get(Opportunity, alpha_id)
        assert opportunity is not None
        opportunity.publication_status = "INTERNAL"
    elif failure_mode == "stale":
        opportunity = session.get(Opportunity, stable_uuid7("beta:opportunity"))
        assert opportunity is not None
        opportunity.current_version = 1
    elif failure_mode == "incomplete":
        session.execute(
            text(
                "UPDATE opportunity_versions SET snapshot = snapshot - 'application_url' "
                "WHERE opportunity_id = :opportunity_id AND version = 1"
            ),
            {"opportunity_id": alpha_id},
        )
    else:
        session.execute(
            text("UPDATE sources SET tier = 'COMMUNITY_SIGNAL' WHERE source_id = :source_id"),
            {"source_id": stable_uuid7("alpha:source")},
        )
    session.flush()

    page = PublicCatalogService(session).list_opportunities(PublicOpportunityQuery())

    assert page.count == 2
    if failure_mode == "stale":
        assert public_ids[1] not in {item.public_id for item in page.items}
    else:
        assert public_ids[0] not in {item.public_id for item in page.items}


def test_detail_exposes_official_evidence_and_ordered_change_history(session: Session) -> None:
    public_ids = persist_phase5_fixture(session)
    service = PublicCatalogService(session)

    detail = service.get_opportunity(public_ids[1])

    assert detail is not None
    assert detail.current_version == 2
    assert str(detail.application_url) == "https://phase5-fixture.example.test/beta/apply"
    assert len(detail.attachment_urls) == 1
    assert {item.field_path for item in detail.key_evidence} >= {
        "canonical_title",
        "status",
        "application_window.closes_on",
        "application_url",
    }
    assert all(item.precedence == 400 for item in detail.key_evidence)
    assert all(item.authority == "ORIGINAL_OFFICIAL_NOTICE" for item in detail.key_evidence)
    assert all(
        str(item.official_url).startswith("https://phase5-fixture.example.test/")
        for item in detail.key_evidence
    )
    assert [item.event_type for item in detail.history] == ["CREATED", "DEADLINE_CHANGED"]
    assert [item.to_version for item in detail.history] == [1, 2]
    assert (
        detail.personalization_availability is PersonalizationAvailability.PHASE_6_NOT_IMPLEMENTED
    )


def test_unknown_or_non_visible_detail_returns_none(session: Session) -> None:
    public_ids = persist_phase5_fixture(session)
    opportunity = session.scalar(select(Opportunity).where(Opportunity.public_id == public_ids[0]))
    assert opportunity is not None
    opportunity.publication_status = "WITHDRAWN"
    session.flush()
    service = PublicCatalogService(session)

    assert service.get_opportunity(public_ids[0]) is None
    assert service.get_opportunity("opp_ffffffffffffffffffffffffffffffff") is None


def test_public_models_exclude_private_phase4_and_storage_fields(session: Session) -> None:
    public_ids = persist_phase5_fixture(session)
    detail = PublicCatalogService(session).get_opportunity(public_ids[0])
    assert detail is not None

    payload = detail.model_dump(mode="json")
    serialized = str(payload).lower()
    for forbidden in (
        "storage_uri",
        "object_key",
        "extracted_text_uri",
        "reviewed_by",
        "profile",
        "eligibility",
        "match_percentage",
        "model_confidence",
        "rule_result",
    ):
        assert forbidden not in serialized

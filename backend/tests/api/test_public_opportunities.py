from collections.abc import Iterator
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from pydantic import HttpUrl
from sqlalchemy.exc import OperationalError

from deepaha.api.public_opportunities import get_public_catalog_service
from deepaha.api.public_opportunities import router as public_opportunities_router
from deepaha.contracts.phase1 import OpportunityStatus
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.main import create_app
from deepaha.public_catalog.cursor import InvalidCursor
from deepaha.public_catalog.schemas import (
    PublicDataLabel,
    PublicEvidence,
    PublicFieldChange,
    PublicHistoryEvent,
    PublicOpportunityCard,
    PublicOpportunityDetail,
    PublicOpportunityPage,
    PublicOpportunityQuery,
)

NOW = datetime(2026, 8, 22, 3, 0, tzinfo=UTC)
PUBLIC_ID = "opp_0123456789abcdef0123456789abcdef"


def public_card() -> PublicOpportunityCard:
    return PublicOpportunityCard(
        public_id=PUBLIC_ID,
        title="合成青年机会",
        type=OpportunityTypeV02.YOUTH_DEVELOPMENT_PROGRAM,
        jurisdiction="合成浙江省",
        locations=("合成杭州市",),
        issuer_name="合成公共机构",
        status=OpportunityStatus.OPEN,
        published_at=NOW,
        deadline=date(2026, 9, 20),
        last_verified_at=NOW,
        change_markers=("DEADLINE_CHANGED",),
        data_label=PublicDataLabel.LICENSE_SAFE_FIXTURE,
    )


def public_detail() -> PublicOpportunityDetail:
    card = public_card()
    evidence_id = UUID("019d0000-0000-7000-8000-000000000001")
    document_id = UUID("019d0000-0000-7000-8000-000000000002")
    return PublicOpportunityDetail(
        **card.model_dump(),
        current_version=2,
        application_url=HttpUrl("https://phase5-fixture.example.test/apply"),
        attachment_urls=(HttpUrl("https://phase5-fixture.example.test/conditions.pdf"),),
        key_evidence=(
            PublicEvidence(
                field_path="application_url",
                evidence_ref_id=evidence_id,
                document_id=document_id,
                locator_kind="full_document",
                locator_value="*",
                locator_payload=None,
                quote_sha256="1" * 64,
                precedence=400,
                authority="ORIGINAL_OFFICIAL_NOTICE",
                official_url=HttpUrl("https://phase5-fixture.example.test/notice"),
            ),
        ),
        history=(
            PublicHistoryEvent(
                event_id=UUID("019d0000-0000-7000-8000-000000000003"),
                from_version=1,
                to_version=2,
                event_type="DEADLINE_CHANGED",
                changed_fields=("application_window.closes_on",),
                changes=(
                    PublicFieldChange(
                        field_path="application_window.closes_on",
                        before="2026-09-10",
                        after="2026-09-20",
                    ),
                ),
                detected_at=NOW,
                evidence_ref_id=evidence_id,
                document_id=document_id,
                official_url=HttpUrl("https://phase5-fixture.example.test/notice"),
            ),
        ),
    )


class FakePublicCatalogService:
    def __init__(self) -> None:
        self.last_query: PublicOpportunityQuery | None = None
        self.fail = False

    def list_opportunities(self, query: PublicOpportunityQuery) -> PublicOpportunityPage:
        self.last_query = query
        if query.cursor == "bad":
            raise InvalidCursor("synthetic invalid cursor detail")
        if self.fail:
            raise OperationalError("SELECT secret_table", {}, RuntimeError("db unavailable"))
        card = public_card()
        return PublicOpportunityPage(
            items=(card,),
            next_cursor="next-cursor",
            count=1,
            data_labels=(PublicDataLabel.LICENSE_SAFE_FIXTURE,),
            reproduced_at=card.last_verified_at,
        )

    def get_opportunity(self, public_id: str) -> PublicOpportunityDetail | None:
        if self.fail:
            raise OperationalError("SELECT secret_table", {}, RuntimeError("db unavailable"))
        return public_detail() if public_id == PUBLIC_ID else None


@pytest.fixture
def api_client() -> Iterator[tuple[TestClient, FakePublicCatalogService]]:
    application = create_app()
    service = FakePublicCatalogService()
    application.dependency_overrides[get_public_catalog_service] = lambda: service
    with TestClient(application) as client:
        yield client, service
    application.dependency_overrides.clear()


def test_list_response_and_query_contract(
    api_client: tuple[TestClient, FakePublicCatalogService],
) -> None:
    client, service = api_client

    response = client.get(
        "/api/v1/public/opportunities",
        params={
            "q": " 青年 ",
            "type": "YOUTH_DEVELOPMENT_PROGRAM",
            "status": "OPEN",
            "region": " 合成浙江省 ",
            "sort": "DEADLINE_ASC",
            "limit": "10",
        },
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=60, stale-while-revalidate=300"
    assert response.json()["items"][0]["public_id"] == PUBLIC_ID
    assert response.json()["data_labels"] == ["LICENSE_SAFE_FIXTURE"]
    assert service.last_query is not None
    assert service.last_query.q == "青年"
    assert service.last_query.region == "合成浙江省"
    assert service.last_query.limit == 10


@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=51",
        "sort=POPULAR",
        "status=PERSONALLY_ELIGIBLE",
        "q=%20%20%20",
        "unknown=value",
        "q=a&q=b",
    ],
)
def test_invalid_query_returns_stable_400_problem(
    api_client: tuple[TestClient, FakePublicCatalogService],
    query: str,
) -> None:
    client, _ = api_client

    response = client.get(f"/api/v1/public/opportunities?{query}")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "https://deepaha.example/problems/invalid-public-query",
        "title": "Invalid public opportunity query",
        "status": 400,
        "detail": "The public opportunity query is invalid.",
        "instance": "/api/v1/public/opportunities",
    }


def test_invalid_cursor_does_not_leak_internal_error_detail(
    api_client: tuple[TestClient, FakePublicCatalogService],
) -> None:
    client, _ = api_client

    response = client.get("/api/v1/public/opportunities?cursor=bad")

    assert response.status_code == 400
    assert "synthetic" not in response.text.lower()
    assert response.json()["type"].endswith("invalid-public-cursor")


def test_detail_and_unknown_id_contract(
    api_client: tuple[TestClient, FakePublicCatalogService],
) -> None:
    client, _ = api_client

    response = client.get(f"/api/v1/public/opportunities/{PUBLIC_ID}")
    missing = client.get("/api/v1/public/opportunities/opp_ffffffffffffffffffffffffffffffff")

    assert response.status_code == 200
    assert response.json()["personalization_availability"] == "PHASE_6_NOT_IMPLEMENTED"
    assert response.json()["history"][0]["event_type"] == "DEADLINE_CHANGED"
    assert missing.status_code == 404
    assert missing.headers["content-type"].startswith("application/problem+json")


def test_dependency_failure_returns_non_sensitive_503(
    api_client: tuple[TestClient, FakePublicCatalogService],
) -> None:
    client, service = api_client
    service.fail = True

    response = client.get("/api/v1/public/opportunities")

    assert response.status_code == 503
    assert response.json()["detail"] == "The public opportunity catalog is temporarily unavailable."
    assert "secret_table" not in response.text
    assert "db unavailable" not in response.text


def test_pre_route_database_failure_returns_non_sensitive_503() -> None:
    application = create_app()

    def unavailable_dependency() -> FakePublicCatalogService:
        raise OperationalError("CONNECT secret_database", {}, RuntimeError("connection secret"))

    application.dependency_overrides[get_public_catalog_service] = unavailable_dependency
    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/api/v1/public/opportunities")

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["detail"] == "The public opportunity catalog is temporarily unavailable."
    assert "secret_database" not in response.text
    assert "connection secret" not in response.text


def test_public_route_surface_is_get_only_and_has_no_phase6_payload() -> None:
    public_routes = [
        route
        for route in public_opportunities_router.routes
        if getattr(route, "path", "").startswith("/api/v1/public/")
    ]

    assert public_routes
    assert all(getattr(route, "methods", set()) == {"GET"} for route in public_routes)
    serialized = public_detail().model_dump_json().lower()
    for forbidden in (
        "eligible",
        "match_percentage",
        "model_confidence",
        "profile",
        "personal_ranking",
        "action_plan",
    ):
        assert forbidden not in serialized

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from deepaha.acquisition.contracts import SourceUsageRole
from deepaha.api.local_human_test import (
    get_local_fact_review_service,
    get_local_item_query,
    get_local_provider_config_store,
    get_local_provisional_service,
    get_local_publication_service,
    get_local_recipe_views,
    get_local_rule_review_service,
    get_local_run_query,
    get_local_run_service,
    require_local_test_principal,
)
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.core.settings import Settings, get_settings
from deepaha.local_human_test.bootstrap import ActiveRecipeView
from deepaha.local_human_test.provider_config import ProviderConfigStatus
from deepaha.local_human_test.runs import RunIdempotencyConflict
from deepaha.main import create_app
from deepaha.review.auth import ReviewerPrincipal, ReviewerRole

NOW = datetime(2026, 8, 26, 10, 0, tzinfo=UTC)
REVIEWER_ID = UUID("019d0000-0000-7000-8000-000000000801")
RECIPE_ID = UUID("019d0000-0000-7000-8000-000000000802")
SOURCE_ID = UUID("019d0000-0000-7000-8000-000000000803")
ENDPOINT_ID = UUID("019d0000-0000-7000-8000-000000000804")
RUN_ID = UUID("019d0000-0000-7000-8000-000000000805")
ITEM_ID = UUID("019d0000-0000-7000-8000-000000000806")
CANDIDATE_ID = UUID("019d0000-0000-7000-8000-000000000807")
RULE_CANDIDATE_ID = UUID("019d0000-0000-7000-8000-000000000808")
OPPORTUNITY_ID = UUID("019d0000-0000-7000-8000-000000000816")


class ConfiguredProviderStore:
    def status(self) -> ProviderConfigStatus:
        return ProviderConfigStatus(
            configured=True,
            provider="agnes",
            base_url="https://provider.invalid",
            protocol="openai_chat_completions",
            model_id="agnes-chat",
            model_snapshot="agnes-chat-2026-08-26",
            provider_region="cn",
            zero_retention=True,
            training_use=False,
            supports_idempotency=True,
            egress_ready=True,
            updated_at=NOW,
        )


class FakeRunService:
    def __init__(self) -> None:
        self.created_command: object | None = None
        self.created_key: str | None = None
        self.conflict = False
        self.cancelled: UUID | None = None
        self.transitioned: tuple[UUID, object, object, object] | None = None

    def create(self, command: object, *, idempotency_key: str) -> SimpleNamespace:
        if self.conflict:
            raise RunIdempotencyConflict("must not leak sensitive detail")
        self.created_command = command
        self.created_key = idempotency_key
        return _run()

    def request_cancel(self, run_id: UUID) -> SimpleNamespace:
        self.cancelled = run_id
        return _run(status="CANCELLED")

    def transition_item(
        self,
        item_id: UUID,
        *,
        expected: object,
        target: object,
        references: object,
    ) -> SimpleNamespace:
        self.transitioned = (item_id, expected, target, references)
        return _item(status="EXTRACTING", opportunity_id=OPPORTUNITY_ID)


class FakeRunQuery:
    def list_runs(self) -> tuple[SimpleNamespace, ...]:
        return (_run(),)

    def get_run(self, run_id: UUID) -> tuple[SimpleNamespace, tuple[SimpleNamespace, ...]] | None:
        if run_id != RUN_ID:
            return None
        return _run(), (_item(),)


def _run(*, status: str = "CREATED") -> SimpleNamespace:
    return SimpleNamespace(
        run_id=RUN_ID,
        mode="OFFICIAL_REPLAY",
        recipe_ids=[str(RECIPE_ID)],
        provider_config_snapshot={
            "provider": "agnes",
            "model_id": "agnes-chat",
            "model_snapshot": "agnes-chat-2026-08-26",
        },
        budget={
            "official_request_limit": 9,
            "llm_call_limit": 8,
            "max_input_tokens": 12000,
            "max_output_tokens": 3000,
            "timeout_seconds": 90,
            "temperature": 0,
        },
        status=status,
        official_request_count=0,
        llm_call_count=0,
        terminal_reason_code=None,
        created_at=NOW,
        updated_at=NOW,
        completed_at=None,
    )


def _item(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "item_id": ITEM_ID,
        "run_id": RUN_ID,
        "recipe_id": str(RECIPE_ID),
        "status": "CREATED",
        "error_code": None,
        "source_id": None,
        "endpoint_id": None,
        "document_id": None,
        "opportunity_id": None,
        "model_call_id": None,
        "verified_fact_set_id": None,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class FakeItemQuery:
    def list_items(self, run_id: UUID | None = None) -> tuple[SimpleNamespace, ...]:
        assert run_id in {None, RUN_ID}
        return (_item(),)

    def get_item_detail(self, item_id: UUID) -> dict[str, object] | None:
        if item_id != ITEM_ID:
            return None
        return {
            "item": _item(),
            "model_audit": {
                "model_call_id": str(UUID("019d0000-0000-7000-8000-000000000809")),
                "canonical_request_hash": "a" * 64,
                "canonical_message_hashes": ["b" * 64],
                "actual_payload_hash": "c" * 64,
                "egress_decision": "ALLOW",
                "final_status": "SUCCEEDED",
                "terminal_disposition": "COMPLETED",
                "attempts": [
                    {
                        "attempt_number": 1,
                        "outcome": "SUCCEEDED",
                        "input_tokens": 321,
                        "output_tokens": 87,
                        "latency_ms": 420,
                        "cost_status": "COST_NOT_REPORTED",
                        "monetary_cost": None,
                    }
                ],
            },
            "candidates": [
                {
                    "candidate_id": str(CANDIDATE_ID),
                    "field_name": "canonical_title",
                    "raw_value": "示例计划",
                    "normalized_value_candidate": "示例计划",
                    "confidence": 0.98,
                    "abstained": False,
                    "candidate_reason_code": "EXTRACTED",
                    "decision": None,
                    "evidence": [
                        {
                            "evidence_ref_id": str(
                                UUID("019d0000-0000-7000-8000-000000000810")
                            ),
                            "block_id": str(
                                UUID("019d0000-0000-7000-8000-000000000811")
                            ),
                            "document_id": str(
                                UUID("019d0000-0000-7000-8000-000000000812")
                            ),
                            "block_type": "HTML_ELEMENT",
                            "canonical_text_or_value": "官方示例计划",
                            "structural_locator": {"selector": "h1"},
                            "source_tier": "OFFICIAL_PRIMARY",
                            "source_url": "https://official.example.gov.cn/notices/1",
                        }
                    ],
                }
            ],
            "rules": [
                {
                    "rule_candidate_id": str(RULE_CANDIDATE_ID),
                    "proposed_rule_payload": {"field": "age", "operator": "lte"},
                    "decision": None,
                }
            ],
        }

    def get_item(self, item_id: UUID) -> SimpleNamespace | None:
        if item_id != ITEM_ID:
            return None
        return _item(
            status="BOOTSTRAP_REVIEW",
            document_id=UUID("019d0000-0000-7000-8000-000000000818"),
        )


class FakeProvisionalService:
    def create(self, *, document_id: UUID, recipe_id: UUID) -> SimpleNamespace:
        assert document_id == UUID("019d0000-0000-7000-8000-000000000818")
        assert recipe_id == RECIPE_ID
        return SimpleNamespace(
            opportunity=SimpleNamespace(opportunity_id=OPPORTUNITY_ID),
        )


class FakeFactReviewService:
    def __init__(self) -> None:
        self.command: object | None = None

    def decide(
        self,
        command: object,
        principal: ReviewerPrincipal,
        idempotency_key: str,
    ) -> SimpleNamespace:
        assert principal.reviewer_id == REVIEWER_ID
        assert idempotency_key == "fact-decision-1"
        self.command = command
        return SimpleNamespace(
            decision_id=UUID("019d0000-0000-7000-8000-000000000813"),
            candidate_id=CANDIDATE_ID,
            decision="APPROVE",
        )

    def promote(self, item_id: UUID, principal: ReviewerPrincipal) -> SimpleNamespace:
        assert item_id == ITEM_ID
        assert principal.reviewer_id == REVIEWER_ID
        return SimpleNamespace(
            item_id=ITEM_ID,
            verified_fact_set_id=UUID("019d0000-0000-7000-8000-000000000814"),
            promoted_field_names=("canonical_title",),
            retained_unpromoted_decision_count=0,
        )


class FakeRuleReviewService:
    def propose_from_verified_facts(self, item_id: UUID) -> SimpleNamespace:
        assert item_id == ITEM_ID
        return SimpleNamespace(
            item_id=ITEM_ID,
            candidates=(),
            eligibility_ceiling="UNCERTAIN",
        )

    def decide(
        self,
        command: object,
        principal: ReviewerPrincipal,
        idempotency_key: str,
    ) -> SimpleNamespace:
        assert principal.reviewer_id == REVIEWER_ID
        assert idempotency_key == "rule-decision-1"
        return SimpleNamespace(
            decision_id=UUID("019d0000-0000-7000-8000-000000000815"),
            rule_candidate_id=RULE_CANDIDATE_ID,
            decision="REJECT",
            eligibility_ceiling="UNCERTAIN",
        )


class FakePublicationService:
    def preview(self, item_id: UUID) -> SimpleNamespace:
        assert item_id == ITEM_ID
        return SimpleNamespace(
            item_id=ITEM_ID,
            opportunity_id=UUID("019d0000-0000-7000-8000-000000000816"),
            base_version=1,
            approved_field_names=("canonical_title",),
            missing_field_names=(),
            content_use_basis="OFFICIAL_PUBLIC_ACCESS",
            official_evidence_complete=True,
            eligibility_ceiling="UNCERTAIN",
            blocker_codes=(),
            eligible=True,
        )

    def publish(
        self,
        item_id: UUID,
        principal: ReviewerPrincipal,
        idempotency_key: str,
    ) -> SimpleNamespace:
        assert item_id == ITEM_ID
        assert principal.reviewer_id == REVIEWER_ID
        assert idempotency_key == "publish-1"
        return SimpleNamespace(
            decision_id=UUID("019d0000-0000-7000-8000-000000000817"),
            item_id=ITEM_ID,
            opportunity_id=UUID("019d0000-0000-7000-8000-000000000816"),
            opportunity_version=2,
            content_sha256="d" * 64,
            repeated=False,
        )


def _recipe() -> ActiveRecipeView:
    return ActiveRecipeView(
        recipe_id=RECIPE_ID,
        source_id=SOURCE_ID,
        endpoint_id=ENDPOINT_ID,
        authority_name="浙江省示例主管部门",
        jurisdiction="浙江省",
        usage_role=SourceUsageRole.PRIMARY_EVIDENCE,
        official_url="https://official.example.gov.cn/notices",
        official_host="official.example.gov.cn",
        allowed_hosts=("official.example.gov.cn",),
        verified_at=NOW,
        maximum_requests=3,
        opportunity_type_hint=OpportunityTypeV02.RESEARCH_PROGRAM,
    )


@pytest.fixture
def client() -> Iterator[tuple[TestClient, FakeRunService]]:
    application = create_app()
    run_service = FakeRunService()
    application.dependency_overrides[get_settings] = lambda: Settings(
        environment="development",
        reviewer_auth_mode="fixture",
        local_human_test_enabled=True,
        local_human_test_root=Path("C:/local/deepaha-human-test"),
    )
    application.dependency_overrides[require_local_test_principal] = lambda: (
        ReviewerPrincipal(
            reviewer_id=REVIEWER_ID,
            roles=frozenset(
                {
                    ReviewerRole.LOCAL_TEST_OPERATOR,
                    ReviewerRole.VALIDATION_REVIEWER,
                }
            ),
            purposes=frozenset({"OPPORTUNITY_FACT_VALIDATION"}),
            synthetic=False,
        )
    )
    application.dependency_overrides[get_local_provider_config_store] = (
        ConfiguredProviderStore
    )
    application.dependency_overrides[get_local_recipe_views] = lambda: (_recipe(),)
    application.dependency_overrides[get_local_run_service] = lambda: run_service
    application.dependency_overrides[get_local_run_query] = FakeRunQuery
    application.dependency_overrides[get_local_item_query] = FakeItemQuery
    application.dependency_overrides[get_local_fact_review_service] = (
        FakeFactReviewService
    )
    application.dependency_overrides[get_local_rule_review_service] = (
        FakeRuleReviewService
    )
    application.dependency_overrides[get_local_publication_service] = (
        FakePublicationService
    )
    application.dependency_overrides[get_local_provisional_service] = (
        FakeProvisionalService
    )
    with TestClient(application, base_url="http://127.0.0.1") as api:
        yield api, run_service
    application.dependency_overrides.clear()


def test_sources_and_runs_are_read_only_summaries(
    client: tuple[TestClient, FakeRunService],
) -> None:
    api, _service = client

    sources = api.get("/api/v1/local-human-test/sources")
    runs = api.get("/api/v1/local-human-test/runs")
    detail = api.get(f"/api/v1/local-human-test/runs/{RUN_ID}")

    assert sources.status_code == 200
    assert sources.json()[0]["recipe_id"] == str(RECIPE_ID)
    assert runs.status_code == 200
    assert runs.json()[0]["provider"] == "agnes"
    assert detail.status_code == 200
    assert detail.json()["items"][0]["status"] == "CREATED"
    assert "api_key" not in detail.text


def test_create_replay_run_snapshots_provider_and_does_not_execute_work(
    client: tuple[TestClient, FakeRunService],
) -> None:
    api, service = client

    response = api.post(
        "/api/v1/local-human-test/runs",
        json={"mode": "OFFICIAL_REPLAY", "recipe_ids": [str(RECIPE_ID)]},
        headers={"Idempotency-Key": "create-run-1"},
    )

    assert response.status_code == 201
    assert response.json()["status"] == "CREATED"
    assert service.created_key == "create-run-1"
    assert service.created_command is not None
    assert service.created_command.provider.provider == "agnes"
    assert service.created_command.reviewer_id == REVIEWER_ID


def test_live_run_requires_explicit_confirmation(
    client: tuple[TestClient, FakeRunService],
) -> None:
    api, service = client

    response = api.post(
        "/api/v1/local-human-test/runs",
        json={"mode": "LIVE_OFFICIAL", "recipe_ids": [str(RECIPE_ID)]},
        headers={"Idempotency-Key": "create-live-1"},
    )

    assert response.status_code == 400
    assert service.created_command is None


def test_run_idempotency_conflict_is_redacted(
    client: tuple[TestClient, FakeRunService],
) -> None:
    api, service = client
    service.conflict = True

    response = api.post(
        "/api/v1/local-human-test/runs",
        json={"mode": "OFFICIAL_REPLAY", "recipe_ids": [str(RECIPE_ID)]},
        headers={"Idempotency-Key": "create-run-conflict"},
    )

    assert response.status_code == 409
    assert "sensitive" not in response.text


def test_item_detail_returns_audit_and_official_evidence_but_not_provider_bytes(
    client: tuple[TestClient, FakeRunService],
) -> None:
    api, _service = client

    listed = api.get(f"/api/v1/local-human-test/items?run_id={RUN_ID}")
    detail = api.get(f"/api/v1/local-human-test/items/{ITEM_ID}")

    assert listed.status_code == 200
    assert listed.json()[0]["item_id"] == str(ITEM_ID)
    assert detail.status_code == 200
    assert detail.json()["model_audit"]["attempts"][0]["input_tokens"] == 321
    assert detail.json()["candidates"][0]["evidence"][0]["source_tier"] == (
        "OFFICIAL_PRIMARY"
    )
    assert "raw_response" not in detail.text
    assert "object_key" not in detail.text


def test_fact_decision_promotes_and_proposes_rules_without_auto_approval(
    client: tuple[TestClient, FakeRunService],
) -> None:
    api, _service = client

    response = api.post(
        f"/api/v1/local-human-test/items/{ITEM_ID}/facts/decision",
        json={
            "candidate_id": str(CANDIDATE_ID),
            "decision": "APPROVE",
            "reason": "官方证据明确支持。",
        },
        headers={"Idempotency-Key": "fact-decision-1"},
    )

    assert response.status_code == 200
    assert response.json()["decision"]["decision"] == "APPROVE"
    assert response.json()["promotion"]["promoted_field_names"] == [
        "canonical_title"
    ]
    assert response.json()["rules"]["eligibility_ceiling"] == "UNCERTAIN"


def test_rule_decision_and_publication_remain_separate_human_actions(
    client: tuple[TestClient, FakeRunService],
) -> None:
    api, _service = client

    rule = api.post(
        f"/api/v1/local-human-test/items/{ITEM_ID}/rules/decision",
        json={
            "rule_candidate_id": str(RULE_CANDIDATE_ID),
            "decision": "REJECT",
            "reason": "不作为硬资格规则。",
        },
        headers={"Idempotency-Key": "rule-decision-1"},
    )
    published = api.post(
        f"/api/v1/local-human-test/items/{ITEM_ID}/publish",
        headers={"Idempotency-Key": "publish-1"},
    )

    assert rule.status_code == 200
    assert rule.json()["eligibility_ceiling"] == "UNCERTAIN"
    assert published.status_code == 200
    assert published.json()["opportunity_version"] == 2


def test_bootstrap_only_advances_after_deterministic_provisional_target(
    client: tuple[TestClient, FakeRunService],
) -> None:
    api, service = client

    response = api.post(
        f"/api/v1/local-human-test/items/{ITEM_ID}/bootstrap",
        headers={"Idempotency-Key": "bootstrap-1"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "EXTRACTING"
    assert response.json()["opportunity_id"] == str(OPPORTUNITY_ID)
    assert service.transitioned is not None

from collections.abc import Iterator
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select

from deepaha.api.local_human_test import (
    require_local_human_test,
    require_local_idempotency_key,
    require_local_test_principal,
)
from deepaha.artifacts.local_file import LocalFileObjectStore
from deepaha.artifacts.models import RawArtifact
from deepaha.core.settings import Settings, get_settings
from deepaha.db.session import get_engine, session_factory
from deepaha.investigations.announcement_snapshots import MaterializeAnnouncementSnapshot
from deepaha.investigations.applicability import DecideRuleApplicability
from deepaha.investigations.contracts import (
    BindInvestigation,
    CreateInvestigation,
    DecideInvestigationFact,
    InvestigationError,
    PrepareInvestigationDocuments,
    PrepareInvestigationFacts,
    PromoteInvestigationFacts,
    RegisterInvestigationIdentity,
    RegisterInvestigationPositions,
    ReviewInvestigation,
)
from deepaha.investigations.cross_level_review import CrossLevelReview
from deepaha.investigations.group_applicability_contracts import (
    GroupApplicabilityContext,
    GroupApplicabilityView,
)
from deepaha.investigations.group_applicability_decision_contracts import (
    GroupApplicabilityHistory,
    GroupApplicabilityReceipt,
)
from deepaha.investigations.group_applicability_decisions import DecideGroupApplicability
from deepaha.investigations.group_contracts import (
    GroupSourcePreview,
    GroupSourceRecord,
    RegisterGroupSource,
)
from deepaha.investigations.group_fact_contracts import (
    DecideGroupFact,
    GroupFactRecord,
    PrepareGroupFacts,
    PromoteGroupFacts,
)
from deepaha.investigations.group_inheritance_contracts import GroupInheritancePreview
from deepaha.investigations.group_rule_contracts import GroupRulePreview
from deepaha.investigations.group_rule_review_contracts import (
    DecideGroupRule,
    GroupRuleReviewRecord,
    PrepareGroupRules,
)
from deepaha.investigations.models import InvestigationMaterial
from deepaha.investigations.relation_decisions import DecideRelation
from deepaha.investigations.relation_proposals import ProposeRelation
from deepaha.investigations.rule_contracts import (
    DecideInvestigationRule,
    MaterializeInvestigationUnitPlan,
    PrepareInvestigationRules,
)
from deepaha.investigations.store import InvestigationStore
from deepaha.local_human_test.review import HumanReviewError
from deepaha.review.auth import (
    OPPORTUNITY_FACT_VALIDATION_PURPOSE,
    ReviewerAuthenticationError,
    ReviewerPrincipal,
    ReviewerRole,
)
from deepaha.sources.models import Source, SourceEndpoint

router = APIRouter(
    prefix="/api/v1/local-human-test/investigations",
    tags=["investigations"],
    dependencies=[Depends(require_local_human_test)],
)


def principal_for_intake(
    principal: Annotated[ReviewerPrincipal, Depends(require_local_test_principal)],
) -> ReviewerPrincipal:
    if (
        OPPORTUNITY_FACT_VALIDATION_PURPOSE not in principal.purposes
        or not principal.roles.intersection(
            {ReviewerRole.LOCAL_TEST_OPERATOR, ReviewerRole.VALIDATION_REVIEWER}
        )
    ):
        raise HTTPException(403, detail={"code": "INVESTIGATION_ROLE_REQUIRED"})
    return principal


def get_investigation_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> Iterator[InvestigationStore]:
    if settings.local_human_test_root is None:
        raise HTTPException(404, detail={"code": "LOCAL_HUMAN_TEST_NOT_FOUND"})
    engine = get_engine(settings)
    try:
        yield InvestigationStore(
            session_factory(engine),
            LocalFileObjectStore(
                root=settings.local_human_test_root / "investigation-objects",
                bucket="deepaha-investigations",
            ),
        )
    finally:
        engine.dispose()


StoreDep = Annotated[InvestigationStore, Depends(get_investigation_store)]
PrincipalDep = Annotated[ReviewerPrincipal, Depends(principal_for_intake)]
KeyDep = Annotated[str, Depends(require_local_idempotency_key)]


def problem(error: Exception) -> HTTPException:
    code = getattr(error, "code", "INVESTIGATION_AUTHORITY_REQUIRED")
    status = (
        404
        if code
        in {
            "INVESTIGATION_NOT_FOUND",
            "UNIT_PLAN_NOT_FOUND",
            "RULE_APPLICABILITY_SOURCE_NOT_FOUND",
            "ANNOUNCEMENT_SNAPSHOT_NOT_FOUND",
            "GROUP_SOURCE_NOT_FOUND",
            "GROUP_FACT_SOURCE_NOT_FOUND",
            "GROUP_FACT_PREPARATION_NOT_FOUND",
            "GROUP_RULE_PREPARATION_NOT_FOUND",
            "RELATION_PROPOSAL_NOT_FOUND",
        }
        else 409
    )
    if (
        isinstance(error, (HumanReviewError, ReviewerAuthenticationError))
        or code == "HUMAN_VALIDATION_AUTHORITY_REQUIRED"
        or code == "RELATION_INDEPENDENT_REVIEW_REQUIRED"
    ):
        status = 403
    return HTTPException(
        status, detail={"code": code}, headers={"Cache-Control": "private, no-store"}
    )


@router.get("")
def list_tasks(store: StoreDep, principal: PrincipalDep, response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store"
    return {"tasks": store.list_tasks()}


@router.post("/{task_id}/relation-proposals")
def create_relation_proposal(
    task_id: UUID,
    command: ProposeRelation,
    store: StoreDep,
    principal: PrincipalDep,
    key: KeyDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.relation_proposals import save_relation_proposal

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return save_relation_proposal(store, task_id, command, principal, key)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get("/{task_id}/unit-plans/{plan_id}/relation-proposal-context")
def read_relation_proposal_context(
    task_id: UUID,
    plan_id: UUID,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
    after: str | None = None,
) -> dict[str, Any]:
    from deepaha.investigations.relation_proposals import read_proposal_context

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return read_proposal_context(store, task_id, plan_id, principal, after)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get("/{task_id}/unit-plans/{plan_id}/relation-proposals")
def read_relation_proposal_index(
    task_id: UUID,
    plan_id: UUID,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.relation_proposals import list_relation_proposals

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return list_relation_proposals(store, task_id, plan_id, principal)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get("/{task_id}/relation-proposals/{proposal_id}")
def read_relation_proposal(
    task_id: UUID,
    proposal_id: UUID,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.relation_proposals import load_relation_proposal

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return load_relation_proposal(store, task_id, proposal_id, principal)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/relation-decisions")
def create_relation_decision(
    task_id: UUID,
    command: DecideRelation,
    store: StoreDep,
    principal: PrincipalDep,
    key: KeyDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.relation_decisions import save_relation_decision

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return save_relation_decision(store, task_id, command, principal, key)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get("/sources")
def list_sources(store: StoreDep, principal: PrincipalDep, response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store"
    with store.factory() as session:
        rows = session.execute(
            select(Source, SourceEndpoint)
            .join(SourceEndpoint, SourceEndpoint.source_id == Source.source_id)
            .where(
                Source.active.is_(True),
                SourceEndpoint.active.is_(True),
                Source.tier == "OFFICIAL_PRIMARY",
                SourceEndpoint.robots_decision.in_(("ALLOWED", "NOT_APPLICABLE")),
                SourceEndpoint.content_use_basis.in_(("OFFICIAL_PUBLIC_ACCESS", "OPEN_LICENSE")),
            )
        )
        return {
            "sources": [
                {
                    "source_id": str(source.source_id),
                    "endpoint_id": str(endpoint.endpoint_id),
                    "authority_name": source.authority_name,
                    "url": endpoint.url,
                    "allowed_hosts": endpoint.allowed_hosts,
                }
                for source, endpoint in rows
            ]
        }


@router.post("", status_code=201)
def create_task(
    command: CreateInvestigation,
    store: StoreDep,
    principal: PrincipalDep,
    key: KeyDep,
    response: Response,
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return store.get(store.create(command, principal, key))
    except (InvestigationError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get("/binding-targets")
def binding_targets(store: StoreDep, principal: PrincipalDep, response: Response) -> dict[str, Any]:
    from deepaha.investigations.bindings import binding_targets as targets

    response.headers["Cache-Control"] = "private, no-store"
    return {"targets": targets(store)}


@router.post("/{task_id}/bindings")
def bind_task(
    task_id: UUID,
    command: BindInvestigation,
    store: StoreDep,
    principal: PrincipalDep,
    key: KeyDep,
    response: Response,
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return store.bind(task_id, command, principal, key)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get("/{task_id}")
def task_detail(
    task_id: UUID, store: StoreDep, principal: PrincipalDep, response: Response
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return store.get(task_id)
    except InvestigationError as error:
        raise problem(error) from None


@router.post("/{task_id}/identity")
def register_identity(
    task_id: UUID,
    command: RegisterInvestigationIdentity,
    store: StoreDep,
    principal: PrincipalDep,
    key: KeyDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.registration import register_identity as register

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return register(store, task_id, command, principal, key)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/positions")
def register_positions(
    task_id: UUID,
    command: RegisterInvestigationPositions,
    store: StoreDep,
    principal: PrincipalDep,
    key: KeyDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.registration import register_positions as register

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return register(store, task_id, command, principal, key)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/facts")
def prepare_facts(
    task_id: UUID,
    command: PrepareInvestigationFacts,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.facts import prepare_facts as prepare

    response.headers["Cache-Control"] = "private, no-store"
    try:
        prepare(store, task_id, command, principal)
        return store.get(task_id)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/facts/decisions")
def decide_fact(
    task_id: UUID,
    command: DecideInvestigationFact,
    store: StoreDep,
    principal: PrincipalDep,
    key: KeyDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.facts import act_on_facts

    response.headers["Cache-Control"] = "private, no-store"
    try:
        act_on_facts(store, task_id, command, principal, key)
        return store.get(task_id)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/facts/promotions")
def promote_facts(
    task_id: UUID,
    command: PromoteInvestigationFacts,
    store: StoreDep,
    principal: PrincipalDep,
    key: KeyDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.facts import act_on_facts

    response.headers["Cache-Control"] = "private, no-store"
    try:
        act_on_facts(store, task_id, command, principal, key)
        return store.get(task_id)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/rules")
def prepare_rules(
    task_id: UUID,
    command: PrepareInvestigationRules,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.rules import prepare_rules as prepare

    response.headers["Cache-Control"] = "private, no-store"
    try:
        prepare(store, task_id, command, principal)
        return store.get(task_id)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/rules/decisions")
def decide_rule(
    task_id: UUID,
    command: DecideInvestigationRule,
    store: StoreDep,
    principal: PrincipalDep,
    key: KeyDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.rules import decide_rule as decide

    response.headers["Cache-Control"] = "private, no-store"
    try:
        decide(store, task_id, command, principal, key)
        return store.get(task_id)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/review")
def review_task(
    task_id: UUID,
    command: ReviewInvestigation,
    store: StoreDep,
    principal: PrincipalDep,
    key: KeyDep,
    response: Response,
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return store.review(task_id, command, principal, key)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/unit-plans")
def prepare_unit_plan(
    task_id: UUID,
    command: MaterializeInvestigationUnitPlan,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.unit_snapshots import materialize_unit_plan

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return materialize_unit_plan(store, task_id, command, principal)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get("/{task_id}/unit-plans/{plan_id}")
def read_unit_plan(
    task_id: UUID,
    plan_id: UUID,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.unit_snapshots import load_unit_plan

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return load_unit_plan(store, task_id, plan_id, principal)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get("/{task_id}/group-source-input", response_model=GroupSourcePreview)
def group_source_input(
    task_id: UUID, entity_id: str, store: StoreDep, principal: PrincipalDep, response: Response
) -> dict[str, Any]:
    from deepaha.investigations.group_bindings import preview_group_source

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return preview_group_source(store, task_id, entity_id, principal)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/group-bindings/{group_binding_id}/facts", response_model=GroupFactRecord)
def prepare_group_fact_review(
    task_id: UUID,
    group_binding_id: UUID,
    command: PrepareGroupFacts,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.group_facts import prepare_group_facts

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return prepare_group_facts(store, task_id, group_binding_id, command, principal)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get("/{task_id}/group-facts/{preparation_id}", response_model=GroupFactRecord)
def read_group_fact_review(
    task_id: UUID,
    preparation_id: UUID,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.group_facts import load_group_facts

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return load_group_facts(store, task_id, preparation_id, principal)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get(
    "/{task_id}/group-facts/{preparation_id}/rules/preview", response_model=GroupRulePreview
)
def read_group_rule_preview(
    task_id: UUID,
    preparation_id: UUID,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.group_rules import preview_group_rules

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return preview_group_rules(store, task_id, preparation_id, principal)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/group-facts/{preparation_id}/rules", response_model=GroupRuleReviewRecord)
def prepare_group_rules(
    task_id: UUID,
    preparation_id: UUID,
    command: PrepareGroupRules,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.group_rule_review import prepare_group_rule_review

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return prepare_group_rule_review(store, task_id, preparation_id, command, principal)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get("/{task_id}/group-rules/{preparation_id}", response_model=GroupRuleReviewRecord)
def read_group_rules(
    task_id: UUID,
    preparation_id: UUID,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.group_rule_review import load_group_rule_review

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return load_group_rule_review(store, task_id, preparation_id, principal)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post(
    "/{task_id}/group-rules/{preparation_id}/decisions", response_model=GroupRuleReviewRecord
)
def decide_group_rules(
    task_id: UUID,
    preparation_id: UUID,
    command: DecideGroupRule,
    store: StoreDep,
    principal: PrincipalDep,
    key: KeyDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.group_rule_review import decide_group_rule

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return decide_group_rule(store, task_id, preparation_id, command, principal, key)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/group-facts/{preparation_id}/decisions", response_model=GroupFactRecord)
def decide_group_fact_review(
    task_id: UUID,
    preparation_id: UUID,
    command: DecideGroupFact,
    store: StoreDep,
    principal: PrincipalDep,
    key: KeyDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.group_facts import act_on_group_facts

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return act_on_group_facts(store, task_id, preparation_id, command, principal, key)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/group-facts/{preparation_id}/promotions", response_model=GroupFactRecord)
def promote_group_fact_review(
    task_id: UUID,
    preparation_id: UUID,
    command: PromoteGroupFacts,
    store: StoreDep,
    principal: PrincipalDep,
    key: KeyDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.group_facts import act_on_group_facts

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return act_on_group_facts(store, task_id, preparation_id, command, principal, key)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/group-bindings", response_model=GroupSourceRecord)
def create_group_source(
    task_id: UUID,
    command: RegisterGroupSource,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.group_bindings import register_group_source

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return register_group_source(
            store, task_id, command.entity_id, command.expected_source_hash, principal
        )
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get("/{task_id}/group-bindings/{group_binding_id}", response_model=GroupSourceRecord)
def read_group_source(
    task_id: UUID,
    group_binding_id: UUID,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.group_bindings import load_group_source

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return load_group_source(store, task_id, group_binding_id, principal)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get("/{task_id}/unit-plans/{plan_id}/announcement-snapshot-input")
def announcement_snapshot_input(
    task_id: UUID, plan_id: UUID, store: StoreDep, principal: PrincipalDep, response: Response
) -> dict[str, Any]:
    from deepaha.investigations.announcement_snapshots import preview_announcement_snapshot

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return preview_announcement_snapshot(store, task_id, plan_id, principal)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/unit-plans/{plan_id}/announcement-snapshots")
def create_announcement_snapshot(
    task_id: UUID,
    plan_id: UUID,
    command: MaterializeAnnouncementSnapshot,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.announcement_snapshots import materialize_announcement_snapshot

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return materialize_announcement_snapshot(
            store, task_id, plan_id, command.expected_dependencies_hash, principal
        )
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get("/{task_id}/announcement-snapshots/{snapshot_id}")
def read_announcement_snapshot(
    task_id: UUID, snapshot_id: UUID, store: StoreDep, principal: PrincipalDep, response: Response
) -> dict[str, Any]:
    from deepaha.investigations.announcement_snapshots import load_announcement_snapshot

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return load_announcement_snapshot(store, task_id, snapshot_id, principal)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get("/{task_id}/unit-plans/{plan_id}/rule-applicability/{source_id}/{candidate_id}")
def read_rule_applicability(
    task_id: UUID,
    plan_id: UUID,
    source_id: UUID,
    candidate_id: UUID,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
    after: str | None = None,
) -> dict[str, Any]:
    from deepaha.investigations.applicability import read_rule_applicability as read

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return read(store, task_id, plan_id, source_id, candidate_id, principal, after=after)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get(
    "/{task_id}/unit-plans/{plan_id}/group-rule-applicability/{source_id}/{candidate_id}",
    response_model=GroupApplicabilityView,
)
def read_group_rule_applicability(
    task_id: UUID,
    plan_id: UUID,
    source_id: UUID,
    candidate_id: UUID,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
    after: str | None = None,
) -> dict[str, Any]:
    from deepaha.investigations.group_applicability import read_group_rule_applicability as read

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return read(store, task_id, plan_id, source_id, candidate_id, principal, after=after)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get(
    "/{task_id}/unit-plans/{plan_id}/group-inheritance-preview",
    response_model=GroupInheritancePreview,
)
def read_group_inheritance_preview(
    task_id: UUID,
    plan_id: UUID,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.group_inheritance import preview_group_inheritance

    response.headers["Cache-Control"] = "private, no-store"
    try:
        result = preview_group_inheritance(store, task_id, plan_id, principal)
        if result["dependencies"]["group_source"]["source"]["task_id"] != str(task_id) or result[
            "snapshot"
        ]["base_v2"]["plan_id"] != str(plan_id):
            raise InvestigationError("GROUP_INHERITANCE_IDENTITY_CONFLICT")
        return result
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get(
    "/{task_id}/unit-plans/{plan_id}/cross-level-preview",
    response_model=CrossLevelReview,
)
def read_cross_level_preview(
    task_id: UUID,
    plan_id: UUID,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.cross_level_preview import preview_cross_level

    response.headers["Cache-Control"] = "private, no-store"
    try:
        result = preview_cross_level(store, task_id, plan_id, principal)
        group = result["dependencies"]["group"]
        if group["dependencies"]["group_source"]["source"]["task_id"] != str(task_id) or group[
            "snapshot"
        ]["base_v2"]["plan_id"] != str(plan_id):
            raise InvestigationError("CROSS_LEVEL_IDENTITY_CONFLICT")
        return result
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get(
    "/{task_id}/unit-plans/{plan_id}/group-rule-contexts",
    response_model=list[GroupApplicabilityContext],
)
def list_group_rule_contexts(
    task_id: UUID,
    plan_id: UUID,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> list[dict[str, Any]]:
    from deepaha.investigations.group_applicability import list_group_rule_contexts as read

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return read(store, task_id, plan_id, principal)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get(
    "/{task_id}/unit-plans/{plan_id}/group-applicability-decisions/{source_id}/{candidate_id}",
    response_model=GroupApplicabilityHistory,
)
def read_group_applicability_decisions(
    task_id: UUID,
    plan_id: UUID,
    source_id: UUID,
    candidate_id: UUID,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.group_applicability_decisions import (
        load_group_applicability_decisions,
    )

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return load_group_applicability_decisions(
            store, task_id, plan_id, source_id, candidate_id, principal
        )
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/group-applicability-decisions", response_model=GroupApplicabilityReceipt)
def decide_group_applicability(
    task_id: UUID,
    command: DecideGroupApplicability,
    store: StoreDep,
    principal: PrincipalDep,
    key: KeyDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.group_applicability_decisions import save_group_applicability

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return save_group_applicability(store, task_id, command, principal, key)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/rule-applicability")
def decide_rule_applicability(
    task_id: UUID,
    command: DecideRuleApplicability,
    store: StoreDep,
    principal: PrincipalDep,
    key: KeyDep,
    response: Response,
) -> dict[str, Any]:
    from deepaha.investigations.applicability import save_rule_applicability

    response.headers["Cache-Control"] = "private, no-store"
    try:
        return save_rule_applicability(store, task_id, command, principal, key)
    except (InvestigationError, HumanReviewError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.post("/{task_id}/documents")
def prepare_documents(
    task_id: UUID,
    command: PrepareInvestigationDocuments,
    store: StoreDep,
    principal: PrincipalDep,
    response: Response,
) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return store.prepare_documents(task_id, command.delivery_hash, principal)
    except (InvestigationError, ReviewerAuthenticationError) as error:
        raise problem(error) from None


@router.get("/{task_id}/materials/{artifact_id}")
def download_material(
    task_id: UUID, artifact_id: str, store: StoreDep, principal: PrincipalDep
) -> Response:
    with store.factory() as session:
        material = session.get(InvestigationMaterial, (task_id, artifact_id))
        raw = None if material is None else session.get(RawArtifact, material.raw_artifact_id)
        if material is None or raw is None:
            raise HTTPException(404, detail={"code": "INVESTIGATION_MATERIAL_NOT_FOUND"})
        content = store.objects.get_bytes(key=raw.object_key)
        expected = str(material.metadata_snapshot["sha256"])
        if sha256(content).hexdigest() != expected:
            raise HTTPException(409, detail={"code": "STORED_MATERIAL_INTEGRITY_FAILED"})
        suffix = PurePosixPath(urlsplit(str(material.metadata_snapshot["url"])).path).suffix.lower()
        if suffix not in (
            ".pdf",
            ".doc",
            ".docx",
            ".xls",
            ".xlsx",
            ".html",
            ".txt",
            ".png",
            ".jpg",
        ):
            suffix = ".bin"
        return Response(
            content,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="original-{expected[:16]}{suffix}"',
                "Cache-Control": "private, no-store",
                "X-Content-Type-Options": "nosniff",
                "Content-Security-Policy": "sandbox; default-src 'none'",
            },
        )

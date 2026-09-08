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
from deepaha.investigations.models import InvestigationMaterial
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
    status = 404 if code == "INVESTIGATION_NOT_FOUND" else 409
    if isinstance(error, (HumanReviewError, ReviewerAuthenticationError)):
        status = 403
    return HTTPException(status, detail={"code": code})


@router.get("")
def list_tasks(store: StoreDep, principal: PrincipalDep, response: Response) -> dict[str, Any]:
    response.headers["Cache-Control"] = "private, no-store"
    return {"tasks": store.list_tasks()}


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

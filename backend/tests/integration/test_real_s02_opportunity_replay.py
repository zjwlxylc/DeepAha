import json
import os
import socket
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid7

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from deepaha.acquisition.contracts import ValidationResult
from deepaha.acquisition.evaluations import EvaluationService, RecordEvaluationCommand
from deepaha.acquisition.models import AcquisitionEvaluation
from deepaha.acquisition.pipeline import advance_valid_artifact
from deepaha.acquisition.recipes import load_recipe_manifest
from deepaha.acquisition.replay import (
    ControlledDirectoryStore,
    ReplayBinding,
    ReplayRunner,
    ReplayStatus,
    load_replay_manifest,
)
from deepaha.acquisition.validation import ContentValidator
from deepaha.artifacts.models import RawArtifact
from deepaha.artifacts.s3 import S3ObjectStore
from deepaha.contracts.phase1 import OpportunityStatus, SourceTier
from deepaha.contracts.phase2 import OpportunityTypeV02
from deepaha.contracts.phase3 import OpportunityDocumentRole
from deepaha.core.settings import Settings
from deepaha.documents.html import LxmlHtmlParser
from deepaha.documents.models import Document, EvidenceRef
from deepaha.documents.pdf import PypdfDocumentParser
from deepaha.documents.service import DocumentService
from deepaha.documents.spreadsheet import OpenpyxlSpreadsheetParser
from deepaha.opportunities.models import (
    DocumentOpportunityLink,
    Opportunity,
    OpportunityEvent,
    OpportunityVersion,
)
from deepaha.opportunities.service import OpportunityResolutionService
from deepaha.opportunities.types import OpportunityPatch, ResolutionDocument
from deepaha.sources.models import CaptureObservation
from deepaha.sources.registry import import_registry, load_registry_manifest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).parents[3]
MANIFEST = ROOT / "config" / "acquisition" / "real-opportunity-replay.v1.json"
CORPUS = ROOT / "config" / "acquisition" / "real-source-corpus.v1.json"
RECIPES = ROOT / "config" / "acquisition" / "recipes.v1.json"
REGISTRY = ROOT / "config" / "sources" / "phase2-official-endpoints.json"


def test_real_s02_manifest_replays_stable_opportunity_identity(
    migrated_engine: Engine,
) -> None:
    payload: dict[str, object] = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert set(payload) == {
        "schema_version",
        "source_acquisition_entry_id",
        "document",
        "resolution_input",
        "expected",
    }
    assert payload["schema_version"] == "1.0.0"
    document = payload["document"]
    resolution = payload["resolution_input"]
    expected = payload["expected"]
    assert isinstance(document, dict)
    assert isinstance(resolution, dict)
    assert isinstance(expected, dict)
    assert set(document) == {
        "artifact_id",
        "requested_url",
        "retrieved_at",
        "content_sha256",
        "normalized_text_sha256",
        "object_key",
        "byte_size",
        "title",
        "extracted_text_uri",
        "evidence_locator",
    }
    assert set(resolution) == {
        "source_id",
        "source_tier",
        "role",
        "canonical_url",
        "external_id",
        "effective_at",
        "facts",
    }
    assert document["content_sha256"] == (
        "1b12bb32943fff5869d411ef74ca205d60a118cb66f0925017a1c9f3c3659641"
    )
    assert document["normalized_text_sha256"] == (
        "a518c753b038da2ba4d256f0ebf3e36aa90d02eebc67a22e3b787afa99025b42"
    )

    factory = sessionmaker(migrated_engine, expire_on_commit=False)
    document_id, evidence_ref_id = _replay_real_s02_document(factory, payload)
    command = _resolution_command(document_id, evidence_ref_id, resolution)
    service = OpportunityResolutionService(
        session_factory=factory,
        clock=lambda: datetime.fromisoformat(str(expected["resolved_at"])),
        id_factory=uuid7,
    )

    first = service.resolve(command)
    second = service.resolve(command)

    assert second == first
    assert first.disposition == "CREATED"
    assert first.public_id == expected["public_id"]
    assert first.resolution_key == expected["resolution_key"]
    assert first.version == expected["version"] == 1
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(AcquisitionEvaluation)) == 1
        assert session.scalar(select(func.count()).select_from(Document)) == 1
        assert session.scalar(select(func.count()).select_from(EvidenceRef)) == 10
        assert session.scalar(select(func.count()).select_from(Opportunity)) == 1
        assert session.scalar(select(func.count()).select_from(OpportunityVersion)) == 1
        assert session.scalar(select(func.count()).select_from(OpportunityEvent)) == 1
        assert session.scalar(select(func.count()).select_from(DocumentOpportunityLink)) == 1
        opportunity = session.scalar(select(Opportunity))
        assert opportunity is not None
        assert opportunity.status == "UNKNOWN"
        assert opportunity.publication_status == "INTERNAL"


def _replay_real_s02_document(
    factory: sessionmaker[Session],
    payload: dict[str, object],
) -> tuple[UUID, UUID]:
    corpus_root = os.environ.get("DEEPAHA_REAL_SOURCE_CORPUS_ROOT")
    if corpus_root is None:
        pytest.skip("controlled real-source corpus is not mounted")

    manifest = load_replay_manifest(CORPUS)
    entry_id = UUID(str(payload["source_acquisition_entry_id"]))
    entries = tuple(entry for entry in manifest.entries if entry.entry_id == entry_id)
    assert len(entries) == 1
    entry = entries[0]
    document = payload["document"]
    assert isinstance(document, dict)
    assert UUID(str(document["artifact_id"])) == entry.artifact_id
    assert document["requested_url"] == str(entry.original_url)
    assert datetime.fromisoformat(str(document["retrieved_at"])) == entry.fetched_at
    assert document["content_sha256"] == entry.content_sha256
    assert document["object_key"] == entry.object_key
    assert document["byte_size"] == entry.byte_size
    recipes = {recipe.recipe_id: recipe for recipe in load_recipe_manifest(RECIPES).recipes}
    controlled_store = ControlledDirectoryStore(Path(corpus_root))
    body = controlled_store.get_bytes(key=entry.object_key)
    runner = ReplayRunner(
        object_store=controlled_store,
        validator=ContentValidator(),
        parsers=(LxmlHtmlParser(), PypdfDocumentParser(), OpenpyxlSpreadsheetParser()),
        fetcher_versions={
            "deepaha-http": "0.2.0",
            "deepaha-static-http": "1.0.0",
            "deepaha-official-alternative": "1.0.0",
        },
    )

    def reject_network(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("REAL_S02_REPLAY_NETWORK_ATTEMPTED")

    with (
        patch.object(socket, "socket", reject_network),
        patch.object(socket, "create_connection", reject_network),
        patch.object(socket, "getaddrinfo", reject_network),
    ):
        replay = runner.run(
            entry=entry,
            recipe=recipes[entry.recipe_id],
            binding=ReplayBinding(entry.source_id, entry.endpoint_id, entry.artifact_id),
        )
    assert replay.status is ReplayStatus.PASSED
    assert replay.validation_status is not None
    assert replay.parse_outcome == "SUCCEEDED"

    settings = Settings()
    object_store = S3ObjectStore(settings)
    object_store.ensure_bucket()
    object_store.put_bytes_if_absent(
        key=entry.object_key,
        content=body,
        media_type=entry.media_type,
        sha256=entry.content_sha256,
    )
    observation_id = uuid7()
    with factory.begin() as session:
        import_registry(session, load_registry_manifest(REGISTRY))
        session.add(
            RawArtifact(
                artifact_id=entry.artifact_id,
                source_id=entry.source_id,
                requested_url=str(entry.original_url),
                resolved_url=str(entry.final_url),
                retrieved_at=entry.fetched_at,
                http_status=entry.http_status,
                media_type=entry.media_type,
                content_sha256=entry.content_sha256,
                storage_bucket=settings.object_store_bucket,
                object_key=entry.object_key,
                byte_size=entry.byte_size,
                collector_version="0.2.0",
                metadata_schema_version="0.2.0",
            )
        )
        session.flush()
        session.add(
            CaptureObservation(
                observation_id=observation_id,
                collection_run_id=uuid7(),
                attempt_number=1,
                endpoint_id=entry.endpoint_id,
                source_id=entry.source_id,
                requested_url=str(entry.original_url),
                resolved_url=str(entry.final_url),
                started_at=entry.fetched_at,
                completed_at=entry.fetched_at,
                outcome="SUCCEEDED",
                http_status=entry.http_status,
                response_etag=None,
                response_last_modified=None,
                artifact_id=entry.artifact_id,
                error_code=None,
                collector_name=entry.fetcher_name,
                collector_version=entry.fetcher_version,
                policy_version=entry.endpoint_policy_version,
            )
        )
    redirect_chain = (
        (str(entry.original_url),)
        if entry.original_url == entry.final_url
        else (str(entry.original_url), str(entry.final_url))
    )
    validation = ValidationResult.model_validate(
        {
            "status": replay.validation_status,
            "challenge_type": None,
            "discovered_count": len(replay.discovered_urls),
            "diagnostic_codes": replay.diagnostic_codes,
            "metrics": {
                "byte_size": entry.byte_size,
                "discovered_count": len(replay.discovered_urls),
            },
            "validator_name": entry.validator_name,
            "validator_version": entry.validator_version,
            "metrics_schema_version": "1.0.0",
            "contract_version": "1.0.0",
        }
    )
    evaluation = EvaluationService(factory).record(
        RecordEvaluationCommand.model_validate(
            {
                "observation_id": observation_id,
                "strategy_used": entry.strategy,
                "redirect_chain": redirect_chain,
                "manual_intervention": False,
                "validation_result": validation,
                "evaluated_at": entry.fetched_at,
            }
        )
    )
    document_service = DocumentService(
        session_factory=factory,
        object_store=object_store,
        parsers=(LxmlHtmlParser(), PypdfDocumentParser(), OpenpyxlSpreadsheetParser()),
    )
    first = advance_valid_artifact(
        session_factory=factory,
        document_service=document_service,
        acquisition_evaluation_id=evaluation.acquisition_evaluation_id,
    )
    second = advance_valid_artifact(
        session_factory=factory,
        document_service=document_service,
        acquisition_evaluation_id=evaluation.acquisition_evaluation_id,
    )
    assert second.document_id == first.document_id
    assert second.evidence_ref_ids == first.evidence_ref_ids
    assert second.created is False
    assert first.document_id is not None
    assert len(first.evidence_ref_ids) == replay.evidence_locator_count == 10
    assert (
        sha256(
            object_store.get_bytes(
                key=(
                    f"derived/documents/{entry.content_sha256}/{entry.parser_name}/"
                    f"{entry.parser_version}/text.txt"
                )
            )
        ).hexdigest()
        == document["normalized_text_sha256"]
    )
    expected_locator = document["evidence_locator"]
    assert isinstance(expected_locator, dict)
    with factory() as session:
        persisted_document = session.get(Document, first.document_id)
        assert persisted_document is not None
        assert persisted_document.artifact_id == entry.artifact_id
        assert persisted_document.title == document["title"]
        assert persisted_document.extracted_text_uri == document["extracted_text_uri"]
        evidence_ref = session.scalar(
            select(EvidenceRef).where(
                EvidenceRef.document_id == first.document_id,
                EvidenceRef.quote_sha256 == expected_locator["text_sha256"],
            )
        )
        assert evidence_ref is not None
        return first.document_id, evidence_ref.evidence_ref_id


def _resolution_command(
    document_id: UUID,
    evidence_ref_id: UUID,
    resolution: dict[str, object],
) -> ResolutionDocument:
    facts = resolution["facts"]
    assert isinstance(facts, dict)
    return ResolutionDocument(
        document_id=document_id,
        source_id=UUID(str(resolution["source_id"])),
        source_tier=SourceTier(str(resolution["source_tier"])),
        evidence_ref_id=evidence_ref_id,
        role=OpportunityDocumentRole(str(resolution["role"])),
        canonical_url=str(resolution["canonical_url"]),
        external_id=str(resolution["external_id"]),
        references_document_ids=(),
        effective_at=datetime.fromisoformat(str(resolution["effective_at"])),
        facts=OpportunityPatch(
            canonical_title=str(facts["canonical_title"]),
            type=OpportunityTypeV02(str(facts["type"])),
            issuer_name=str(facts["issuer_name"]),
            jurisdiction=str(facts["jurisdiction"]),
            status=OpportunityStatus(str(facts["status"])),
            published_at=datetime.fromisoformat(str(facts["published_at"])),
            application_url=str(facts["application_url"]),
        ),
    )

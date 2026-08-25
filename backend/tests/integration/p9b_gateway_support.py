from dataclasses import dataclass, replace
from datetime import datetime, timedelta
from hashlib import sha256
from uuid import UUID, uuid7

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from deepaha.artifacts.models import RawArtifact
from deepaha.contracts.phase9b import (
    EgressBlockClassificationSchemaV08,
    EgressDecisionSchemaV08,
    ModelCallIntentSchemaV08,
    ModelTaskSpecSchemaV08,
    ProviderEgressPolicySnapshotSchemaV08,
    SourceEgressPolicySnapshotSchemaV08,
)
from deepaha.documents.blocks import ParsedBlock, block_hash, evidence_binding_hash
from deepaha.documents.models import Document, DocumentBlock, EvidenceRef
from deepaha.p9b.egress import EgressRepository
from deepaha.p9b.hashing import document_parse_key
from deepaha.p9b.models import ModelCall
from tests.integration.test_p9b_b0_persistence import NOW, frozen_bundle, seed_graph

P9B_PARSER_NAME = "deepaha-html-p9b"
P9B_PARSER_VERSION = "0.8.0"
P9B_PARSE_CONTRACT = "p9b-document-block-contract-v0.8.0"


@dataclass(frozen=True, slots=True)
class GatewayAuthoritySeed:
    intent: ModelCallIntentSchemaV08
    source_bundle_revision_id: UUID
    expires_at: datetime


def seed_gateway_authority(
    session: Session,
    *,
    expiry_seconds: float = 300,
    max_attempts: int = 2,
    timeout_ms: int = 5000,
    supports_idempotency: bool = False,
) -> GatewayAuthoritySeed:
    graph = seed_graph(session, suffix=f"gateway-{uuid7()}")
    legacy_document = session.get(Document, graph.document_id)
    assert legacy_document is not None
    artifact = session.get(RawArtifact, legacy_document.artifact_id)
    assert artifact is not None

    document_id = uuid7()
    block_id = uuid7()
    evidence_ref_id = uuid7()
    parse_key = document_parse_key(
        artifact_id=artifact.artifact_id,
        artifact_sha256=artifact.content_sha256,
        parser_name=P9B_PARSER_NAME,
        parser_version=P9B_PARSER_VERSION,
        parse_contract_version=P9B_PARSE_CONTRACT,
    )
    value = "Official opportunity fact"
    value_hash = sha256(value.encode()).hexdigest()
    parsed_block = ParsedBlock(
        block_type="HTML_ELEMENT",
        canonical_text_or_value=value,
        structural_locator={
            "kind": "html_element_span",
            "selector": "main:nth-of-type(1) > p:nth-of-type(1)",
            "text_start": 0,
            "text_end": len(value),
        },
        parent_ordinal=None,
    )
    block_hash_value = block_hash(
        document_parse_key=parse_key,
        ordinal=1,
        block=parsed_block,
    )
    binding_hash = evidence_binding_hash(
        block_id=str(block_id),
        document_parse_key=parse_key,
        structural_locator=parsed_block.structural_locator,
        block_hash_value=block_hash_value,
    )
    document = Document(
        document_id=document_id,
        artifact_id=artifact.artifact_id,
        title="Synthetic P9-B block document",
        published_at=NOW,
        language="zh-CN",
        extracted_text_uri=None,
        parser_name=P9B_PARSER_NAME,
        parser_version=P9B_PARSER_VERSION,
        parse_contract_version=P9B_PARSE_CONTRACT,
        document_parse_key=parse_key,
        parse_confidence=None,
        created_at=NOW,
    )
    structural_locator = parsed_block.structural_locator
    evidence = EvidenceRef(
        evidence_ref_id=evidence_ref_id,
        document_id=document_id,
        artifact_id=artifact.artifact_id,
        locator_kind="html_element_span",
        locator_value=None,
        locator_schema_version="0.8.0",
        locator_payload={
            "schema_version": "0.8.0",
            "kind": "html_element_span",
            "block_id": str(block_id),
            "document_parse_key": parse_key,
            "block_type": "HTML_ELEMENT",
            "structural_locator": structural_locator,
            "value_sha256": value_hash,
        },
        quote_sha256=value_hash,
    )
    block = DocumentBlock(
        block_id=block_id,
        document_id=document_id,
        artifact_id=artifact.artifact_id,
        document_parse_key=parse_key,
        ordinal=1,
        block_type="HTML_ELEMENT",
        canonical_text_or_value=value,
        structural_locator=structural_locator,
        block_hash=block_hash_value,
        evidence_binding_hash=binding_hash,
        evidence_ref_id=evidence_ref_id,
        parent_block_id=None,
        parser_name=P9B_PARSER_NAME,
        parser_version=P9B_PARSER_VERSION,
        parse_contract_version=P9B_PARSE_CONTRACT,
        created_at=NOW,
    )
    session.add(document)
    session.flush()
    session.add(evidence)
    session.flush()
    session.add(block)
    session.flush()

    block_graph = replace(graph, document_id=document_id, evidence_ref_id=evidence_ref_id)
    revision = frozen_bundle(session, block_graph)
    database_now = session.scalar(select(text("clock_timestamp()")))
    assert database_now is not None
    task_name = f"extract-{uuid7()}"
    task_version = "v1"
    provider = f"fake-provider-{uuid7()}"
    source_snapshot_id = f"source-policy-{uuid7()}"
    provider_snapshot_id = f"provider-policy-{uuid7()}"
    source_snapshot_hash = sha256(source_snapshot_id.encode()).hexdigest()
    provider_snapshot_hash = sha256(provider_snapshot_id.encode()).hexdigest()
    egress_decision_id = uuid7()
    model_call_id = uuid7()
    valid_until = database_now + timedelta(hours=1)
    decision_expiry = database_now + timedelta(seconds=expiry_seconds)

    EgressRepository(session).persist_task_spec(
        ModelTaskSpecSchemaV08(
            model_task_spec_id=uuid7(),
            task_name=task_name,
            task_version=task_version,
            route_class="R2_BALANCED_REASON",
            allowed_input_block_types=["HTML_ELEMENT"],
            output_schema_version="schema-v1",
            max_input_tokens=2048,
            max_output_tokens=256,
            evidence_required=True,
            abstention_allowed=True,
            risk_class="HIGH_IMPACT_CANDIDATE",
            provider_capabilities=["ZERO_RETENTION"],
            egress_policy_id="p9b-egress-v1",
            timeout_ms=timeout_ms,
            max_attempts=max_attempts,
            initial_backoff_ms=10,
            backoff_multiplier=2.0,
            max_backoff_ms=100,
            max_concurrency=1,
            max_batch_size=1,
            fallback_policy="DISABLED",
            max_fallbacks=0,
            created_at=database_now,
        )
    )
    repository = EgressRepository(session)
    repository.persist_block_classification(
        EgressBlockClassificationSchemaV08(
            classification_id=uuid7(),
            block_id=block_id,
            block_hash=block_hash_value,
            classification_version="classification-v1",
            classifications=["PUBLIC_OFFICIAL_GENERAL"],
            contains_user_data=False,
            classifier_identity="system:classification-v1",
            created_at=database_now,
        )
    )
    repository.persist_source_policy(
        SourceEgressPolicySnapshotSchemaV08(
            snapshot_id=source_snapshot_id,
            snapshot_hash=source_snapshot_hash,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            allows_egress=True,
            valid_from=database_now - timedelta(hours=1),
            valid_until=valid_until,
            recorded_by="human:security-reviewer",
            created_at=database_now,
        )
    )
    repository.persist_provider_policy(
        ProviderEgressPolicySnapshotSchemaV08(
            snapshot_id=provider_snapshot_id,
            snapshot_hash=provider_snapshot_hash,
            provider=provider,
            region="local-test",
            active=True,
            zero_retention=True,
            training_use=False,
            supports_idempotency=supports_idempotency,
            allowed_classifications=["PUBLIC_OFFICIAL_GENERAL"],
            retention_class="ZERO_RETENTION",
            valid_from=database_now - timedelta(hours=1),
            valid_until=valid_until,
            recorded_by="human:security-reviewer",
            created_at=database_now,
        )
    )
    repository.persist_decision(
        EgressDecisionSchemaV08(
            egress_decision_id=egress_decision_id,
            task_spec_name=task_name,
            task_spec_version=task_version,
            source_bundle_revision_id=revision.source_bundle_revision_id,
            target_scope="OPPORTUNITY",
            opportunity_id=graph.opportunity_id,
            opportunity_version=graph.opportunity_version,
            opportunity_unit_id=None,
            opportunity_unit_version_id=None,
            input_block_ids=[block_id],
            input_block_hashes=[block_hash_value],
            data_classification_version="classification-v1",
            minimizer_version="minimizer-v1",
            redactor_version="redactor-v1",
            source_policy_snapshot_id=source_snapshot_id,
            source_policy_snapshot_hash=source_snapshot_hash,
            provider_policy_snapshot_id=provider_snapshot_id,
            provider_policy_snapshot_hash=provider_snapshot_hash,
            provider=provider,
            provider_region="local-test",
            original_input_hash="6" * 64,
            actual_payload_hash="7" * 64,
            decision="ALLOW",
            actor_type="SYSTEM",
            actor_identity=None,
            reason_codes=["POLICY_ALLOW"],
            created_at=database_now,
            expires_at=decision_expiry,
        )
    )
    session.flush()
    intent = ModelCallIntentSchemaV08(
        model_call_id=model_call_id,
        task_spec_name=task_name,
        task_spec_version=task_version,
        provider=provider,
        model_id="fake-model",
        model_snapshot="fake-model-2026-08-25",
        adapter_name="fake-adapter",
        adapter_version="v1",
        runtime_version="python-3.14",
        canonical_request_hash="1" * 64,
        canonical_message_hashes=["2" * 64],
        input_block_ids=[block_id],
        input_block_hashes=[block_hash_value],
        source_bundle_revision_id=revision.source_bundle_revision_id,
        target_scope="OPPORTUNITY",
        opportunity_id=graph.opportunity_id,
        opportunity_version=graph.opportunity_version,
        opportunity_unit_id=None,
        opportunity_unit_version_id=None,
        unit_segmentation_version=None,
        prompt_version="prompt-v1",
        output_schema_version="schema-v1",
        parser_version="parser-v1",
        contract_version="contract-v1",
        temperature=0.0,
        top_p=1.0,
        seed=42,
        egress_decision_id=egress_decision_id,
        validation_pipeline_version="validation-v1",
        retention_class="ZERO_RETENTION",
        registered_at=database_now,
    )
    return GatewayAuthoritySeed(intent, revision.source_bundle_revision_id, decision_expiry)


def persist_model_call(session: Session, intent: ModelCallIntentSchemaV08) -> ModelCall:
    row = ModelCall(**intent.model_dump(mode="python"))
    session.add(row)
    session.flush()
    return row


__all__ = [
    "GatewayAuthoritySeed",
    "persist_model_call",
    "seed_gateway_authority",
]

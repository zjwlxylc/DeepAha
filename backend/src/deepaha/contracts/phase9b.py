from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AfterValidator,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_validator,
)

from deepaha.contracts.common import EntityId, Instant, NonEmptyString, Sha256, VersionNumber
from deepaha.contracts.phase1 import ContractModel
from deepaha.contracts.phase4 import RuleField, RuleOperator, RuleValueType
from deepaha.p9b.hashing import document_parse_key, extraction_input_block_set_hash
from deepaha.p9b.ledger_values import (
    require_error_code,
    require_identifier,
    require_object_key,
    require_provider_response_id,
    require_storage_bucket,
)

LedgerIdentifier32 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=32),
    AfterValidator(require_identifier),
]
LedgerIdentifier64 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64),
    AfterValidator(require_identifier),
]
LedgerIdentifier128 = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128),
    AfterValidator(require_identifier),
]
LedgerProviderResponseId = Annotated[
    str,
    StringConstraints(min_length=1, max_length=256),
    AfterValidator(require_provider_response_id),
]
LedgerStorageBucket = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128),
    AfterValidator(require_storage_bucket),
]
LedgerObjectKey = Annotated[
    str,
    StringConstraints(min_length=1, max_length=512),
    AfterValidator(require_object_key),
]
LedgerErrorCode = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64),
    AfterValidator(require_error_code),
]


class Phase9BContractModel(ContractModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class OpportunityUnitKind(StrEnum):
    POSITION = "POSITION"
    TRACK = "TRACK"
    PROGRAM_TIER = "PROGRAM_TIER"
    REGION_VARIANT = "REGION_VARIANT"
    DEFAULT_SINGLETON = "DEFAULT_SINGLETON"


class OpportunityUnitLifecycleStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"
    IDENTITY_COLLISION = "IDENTITY_COLLISION"


class OpportunityUnitVersionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    SUPERSEDED_BY_SEGMENTATION = "SUPERSEDED_BY_SEGMENTATION"
    MERGED = "MERGED"
    CANCELLED = "CANCELLED"
    WITHDRAWN = "WITHDRAWN"


class OpportunityUnitAliasKind(StrEnum):
    CURRENT = "CURRENT"
    HISTORICAL = "HISTORICAL"
    OFFICIAL_CODE = "OFFICIAL_CODE"
    CANONICAL_DERIVED = "CANONICAL_DERIVED"


class OpportunityUnitLineageEventType(StrEnum):
    REKEY = "REKEY"
    SPLIT = "SPLIT"
    MERGE = "MERGE"
    REVERSAL = "REVERSAL"
    CANCEL = "CANCEL"
    REACTIVATE = "REACTIVATE"


class OpportunityUnitLineageMemberRole(StrEnum):
    SOURCE = "SOURCE"
    TARGET = "TARGET"


class SourceBundleRevisionStatus(StrEnum):
    DRAFT = "DRAFT"
    FROZEN = "FROZEN"
    INVALIDATED = "INVALIDATED"


class SourceBundleMemberRole(StrEnum):
    PRIMARY_NOTICE = "PRIMARY_NOTICE"
    ATTACHMENT = "ATTACHMENT"
    CORRECTION = "CORRECTION"
    SUPPLEMENT = "SUPPLEMENT"
    FAQ = "FAQ"
    CANCELLATION = "CANCELLATION"
    RESULT_NOTICE = "RESULT_NOTICE"


class SourceBundleRelationType(StrEnum):
    PRIMARY = "PRIMARY"
    ATTACHES_TO = "ATTACHES_TO"
    AMENDS = "AMENDS"
    SUPERSEDES = "SUPERSEDES"
    CANCELS = "CANCELS"
    CLARIFIES = "CLARIFIES"


class DatasetPartition(StrEnum):
    CALIBRATION = "CALIBRATION"
    DEVELOPMENT = "DEVELOPMENT"
    VALIDATION = "VALIDATION"
    LOCKED_ACCEPTANCE = "LOCKED_ACCEPTANCE"


class AnswerAccessClass(StrEnum):
    ASSISTED_CALIBRATION = "ASSISTED_CALIBRATION"
    DEVELOPMENT_VISIBLE = "DEVELOPMENT_VISIBLE"
    VALIDATION_BLIND = "VALIDATION_BLIND"
    LOCKED_BLIND = "LOCKED_BLIND"


class GoldReviewRole(StrEnum):
    ANNOTATOR = "ANNOTATOR"
    VERIFIER = "VERIFIER"
    ADJUDICATOR = "ADJUDICATOR"
    CURATOR = "CURATOR"


class GoldFieldState(StrEnum):
    KNOWN_SUPPORTED = "KNOWN_SUPPORTED"
    KNOWN_NOT_APPLICABLE = "KNOWN_NOT_APPLICABLE"
    AMBIGUOUS = "AMBIGUOUS"
    NOT_OBSERVED = "NOT_OBSERVED"


class PredictionFieldState(StrEnum):
    VALUE = "VALUE"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    OMITTED = "OMITTED"


class RetentionClass(StrEnum):
    ZERO_RETENTION = "ZERO_RETENTION"
    PROVIDER_TRANSIENT_RETENTION = "PROVIDER_TRANSIENT_RETENTION"
    INTERNAL_ENCRYPTED_AUDIT = "INTERNAL_ENCRYPTED_AUDIT"


class ModelRouteClass(StrEnum):
    R1_LOW_COST_EXTRACT = "R1_LOW_COST_EXTRACT"
    R2_BALANCED_REASON = "R2_BALANCED_REASON"
    R3_STRONG_CANDIDATE = "R3_STRONG_CANDIDATE"


class EgressDecisionValue(StrEnum):
    ALLOW = "ALLOW"
    REDACT_AND_ALLOW = "REDACT_AND_ALLOW"
    DENY = "DENY"
    LOCAL_NO_EGRESS = "LOCAL_NO_EGRESS"


class RawResponseReferenceKind(StrEnum):
    INTERNAL_OBJECT = "INTERNAL_OBJECT"
    PROVIDER_RESPONSE_ID = "PROVIDER_RESPONSE_ID"


class ModelAttemptOutcome(StrEnum):
    AUTHORITY_REJECTED = "AUTHORITY_REJECTED"
    SUCCEEDED = "SUCCEEDED"
    RETRYABLE_PROVIDER_ERROR = "RETRYABLE_PROVIDER_ERROR"
    TERMINAL_PROVIDER_ERROR = "TERMINAL_PROVIDER_ERROR"
    PROVIDER_OUTCOME_UNKNOWN = "PROVIDER_OUTCOME_UNKNOWN"
    RESPONSE_METADATA_REJECTED = "RESPONSE_METADATA_REJECTED"
    OUTPUT_LIMIT_EXCEEDED = "OUTPUT_LIMIT_EXCEEDED"
    INVALID_JSON_RESPONSE = "INVALID_JSON_RESPONSE"
    INVALID_CANDIDATE_SHAPE = "INVALID_CANDIDATE_SHAPE"
    OUTPUT_SCHEMA_VALIDATION_FAILED = "OUTPUT_SCHEMA_VALIDATION_FAILED"


class ModelCallFinalStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    TERMINAL_FAILED = "TERMINAL_FAILED"


class ModelCallLedgerStatus(StrEnum):
    IN_PROGRESS = "IN_PROGRESS"
    SUCCEEDED = "SUCCEEDED"
    TERMINAL_FAILED = "TERMINAL_FAILED"


class ModelTerminalDisposition(StrEnum):
    COMPLETED = "COMPLETED"
    AUTHORITY_REJECTED = "AUTHORITY_REJECTED"
    PROVIDER_TERMINAL = "PROVIDER_TERMINAL"
    PROVIDER_OUTCOME_UNKNOWN = "PROVIDER_OUTCOME_UNKNOWN"
    RESPONSE_METADATA_REJECTED = "RESPONSE_METADATA_REJECTED"
    ATTEMPTS_EXHAUSTED = "ATTEMPTS_EXHAUSTED"
    REVISION_INVALIDATED_AFTER_DISPATCH = "REVISION_INVALIDATED_AFTER_DISPATCH"


class DocumentBlockType(StrEnum):
    HTML_SECTION = "HTML_SECTION"
    HTML_ELEMENT = "HTML_ELEMENT"
    PDF_TEXT_SPAN = "PDF_TEXT_SPAN"
    PDF_TABLE_CELL = "PDF_TABLE_CELL"
    SPREADSHEET_CELL = "SPREADSHEET_CELL"
    SPREADSHEET_RANGE = "SPREADSHEET_RANGE"
    DOCX_PARAGRAPH = "DOCX_PARAGRAPH"
    DOCX_TABLE_CELL = "DOCX_TABLE_CELL"
    OCR_TEXT_SPAN = "OCR_TEXT_SPAN"


class ExtractionTargetScope(StrEnum):
    OPPORTUNITY = "OPPORTUNITY"
    UNIT = "UNIT"


class ExtractorKind(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    MODEL = "MODEL"
    HYBRID = "HYBRID"


class ExtractionRunStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    ABSTAINED = "ABSTAINED"
    FAILED = "FAILED"


class FactVerificationDecision(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    UNKNOWN = "UNKNOWN"
    NEEDS_ADJUDICATION = "NEEDS_ADJUDICATION"


class VerificationMethod(StrEnum):
    DETERMINISTIC = "DETERMINISTIC"
    HUMAN = "HUMAN"
    APPROVED_MAPPING = "APPROVED_MAPPING"


class EvidenceSupportResult(StrEnum):
    SUPPORTED = "SUPPORTED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class PrecedenceCheckResult(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class VerifiedFactState(StrEnum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


class VerifiedFactSetStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    STALE = "STALE"
    WITHDRAWN = "WITHDRAWN"


class RuleCandidateStatus(StrEnum):
    PROPOSED = "PROPOSED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    SUPERSEDED = "SUPERSEDED"


class RuleApprovalDecisionValue(StrEnum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    NEEDS_ADJUDICATION = "NEEDS_ADJUDICATION"


class RuleApprovalMethod(StrEnum):
    HUMAN = "HUMAN"
    DETERMINISTIC_POLICY = "DETERMINISTIC_POLICY"


def _require_target_shape(
    *,
    target_scope: ExtractionTargetScope,
    opportunity_unit_id: EntityId | None,
    opportunity_unit_version_id: EntityId | None,
    unit_segmentation_version: str | None = None,
) -> None:
    unit_fields_present = (
        opportunity_unit_id is not None and opportunity_unit_version_id is not None
    )
    if target_scope == ExtractionTargetScope.UNIT:
        if not unit_fields_present:
            raise ValueError("UNIT target requires exact unit and unit-version identity")
        if unit_segmentation_version is not None and not unit_segmentation_version.strip():
            raise ValueError("UNIT segmentation version must not be blank")
        return
    if opportunity_unit_id is not None or opportunity_unit_version_id is not None:
        raise ValueError("OPPORTUNITY target forbids unit identity")
    if unit_segmentation_version is not None:
        raise ValueError("OPPORTUNITY target forbids unit segmentation version")


class ExtractionRunSchemaV08(Phase9BContractModel):
    extraction_run_id: EntityId
    source_bundle_revision_id: EntityId
    target_scope: ExtractionTargetScope
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    opportunity_unit_id: EntityId | None
    opportunity_unit_version_id: EntityId | None
    unit_segmentation_version: NonEmptyString | None
    task_spec_version: NonEmptyString
    extractor_kind: ExtractorKind
    component_version: NonEmptyString
    producer_identity: NonEmptyString
    producer_response_id: NonEmptyString | None
    ordered_input_block_ids: list[EntityId] = Field(min_length=1)
    input_block_set_hash: Sha256
    evidence_binding_hash: Sha256
    started_at: Instant
    completed_at: Instant
    status: ExtractionRunStatus

    @model_validator(mode="after")
    def require_exact_bindings(self) -> Self:
        _require_target_shape(
            target_scope=self.target_scope,
            opportunity_unit_id=self.opportunity_unit_id,
            opportunity_unit_version_id=self.opportunity_unit_version_id,
            unit_segmentation_version=self.unit_segmentation_version,
        )
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        expected = extraction_input_block_set_hash(self.ordered_input_block_ids)
        if self.input_block_set_hash != expected:
            raise ValueError("input_block_set_hash does not match ordered input blocks")
        if self.extractor_kind == ExtractorKind.MODEL and self.producer_response_id is None:
            raise ValueError("MODEL extraction requires producer_response_id")
        return self


class ExtractionCandidateSchemaV08(Phase9BContractModel):
    candidate_id: EntityId
    extraction_run_id: EntityId
    target_scope: ExtractionTargetScope
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    opportunity_unit_id: EntityId | None
    opportunity_unit_version_id: EntityId | None
    field_name: NonEmptyString
    raw_value: JsonValue | None
    normalized_value_candidate: JsonValue | None
    evidence_block_ids: list[EntityId] = Field(min_length=1)
    evidence_ref_ids: list[EntityId] = Field(min_length=1)
    confidence: Annotated[float, Field(ge=0, le=1)] | None
    abstained: bool
    candidate_reason_code: NonEmptyString
    schema_version: Literal["0.8.0"]
    created_at: Instant

    @field_validator("evidence_block_ids", "evidence_ref_ids")
    @classmethod
    def require_unique_evidence(cls, value: list[EntityId]) -> list[EntityId]:
        if len(value) != len(set(value)):
            raise ValueError("candidate evidence identities must be unique")
        return value

    @model_validator(mode="after")
    def require_candidate_shape(self) -> Self:
        _require_target_shape(
            target_scope=self.target_scope,
            opportunity_unit_id=self.opportunity_unit_id,
            opportunity_unit_version_id=self.opportunity_unit_version_id,
        )
        if self.abstained:
            if self.normalized_value_candidate is not None:
                raise ValueError("abstained candidate forbids normalized_value_candidate")
            if not self.candidate_reason_code.startswith("UNKNOWN_"):
                raise ValueError("abstained candidate reason must use UNKNOWN_ prefix")
        elif self.normalized_value_candidate is None:
            raise ValueError("non-abstained candidate requires normalized_value_candidate")
        if len(self.evidence_block_ids) != len(self.evidence_ref_ids):
            raise ValueError("candidate block and EvidenceRef counts must match")
        return self


class FactVerificationDecisionSchemaV08(Phase9BContractModel):
    decision_id: EntityId
    candidate_id: EntityId
    decision: FactVerificationDecision
    verification_method: VerificationMethod
    verifier_identity: NonEmptyString
    verifier_response_id: NonEmptyString | None
    reason_code: NonEmptyString
    evidence_support_result: EvidenceSupportResult
    precedence_check_result: PrecedenceCheckResult
    decided_at: Instant

    @model_validator(mode="after")
    def require_approval_support(self) -> Self:
        if self.decision == FactVerificationDecision.APPROVE and (
            self.evidence_support_result != EvidenceSupportResult.SUPPORTED
            or self.precedence_check_result != PrecedenceCheckResult.PASSED
        ):
            raise ValueError("APPROVE requires supported evidence and passed precedence")
        return self


class VerifiedFactSchemaV08(Phase9BContractModel):
    verified_fact_id: EntityId
    verified_fact_set_id: EntityId
    field_name: NonEmptyString
    fact_state: VerifiedFactState
    normalized_value: JsonValue | None
    raw_value: JsonValue | None
    evidence_ref_ids: list[EntityId] = Field(min_length=1)
    verification_decision_id: EntityId
    dependency_fingerprint: Sha256

    @model_validator(mode="after")
    def require_fact_shape(self) -> Self:
        if (self.fact_state == VerifiedFactState.UNKNOWN) != (self.normalized_value is None):
            raise ValueError("UNKNOWN fact is the only fact state without normalized value")
        return self


class VersionedVerifiedFactSetSchemaV08(Phase9BContractModel):
    verified_fact_set_id: EntityId
    target_scope: ExtractionTargetScope
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    opportunity_unit_id: EntityId | None
    opportunity_unit_version_id: EntityId | None
    source_bundle_revision_id: EntityId
    version: VersionNumber
    relation_graph_version: NonEmptyString
    precedence_graph_version: NonEmptyString
    reference_dataset_versions: dict[str, NonEmptyString]
    fact_schema_version: Literal["0.8.0"]
    status: VerifiedFactSetStatus
    supersedes_id: EntityId | None
    facts: list[VerifiedFactSchemaV08] = Field(min_length=1)
    created_at: Instant

    @model_validator(mode="after")
    def require_fact_set_shape(self) -> Self:
        _require_target_shape(
            target_scope=self.target_scope,
            opportunity_unit_id=self.opportunity_unit_id,
            opportunity_unit_version_id=self.opportunity_unit_version_id,
        )
        if any(fact.verified_fact_set_id != self.verified_fact_set_id for fact in self.facts):
            raise ValueError("all facts must belong to the fact set")
        return self


class ProposedRulePayloadSchemaV08(Phase9BContractModel):
    code: NonEmptyString
    operator: RuleOperator
    field: RuleField
    value_type: RuleValueType
    value: JsonValue | None
    required: bool
    reason_template: NonEmptyString

    @model_validator(mode="after")
    def require_value_shape(self) -> Self:
        if self.operator in {RuleOperator.EXISTS, RuleOperator.NOT_EXISTS}:
            if self.value is not None:
                raise ValueError("existence operator forbids value")
        elif self.value is None:
            raise ValueError("atomic rule requires value")
        return self


class RuleCandidateSchemaV08(Phase9BContractModel):
    rule_candidate_id: EntityId
    target_scope: ExtractionTargetScope
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    opportunity_unit_id: EntityId | None
    opportunity_unit_version_id: EntityId | None
    verified_fact_ids: list[EntityId] = Field(min_length=1)
    rule_type: Literal["ATOMIC_QUALIFICATION"]
    proposed_rule_payload: ProposedRulePayloadSchemaV08
    evidence_ref_ids: list[EntityId] = Field(min_length=1)
    compiler_version: NonEmptyString
    producer_identity: NonEmptyString
    status: RuleCandidateStatus
    created_at: Instant

    @model_validator(mode="after")
    def require_rule_target(self) -> Self:
        _require_target_shape(
            target_scope=self.target_scope,
            opportunity_unit_id=self.opportunity_unit_id,
            opportunity_unit_version_id=self.opportunity_unit_version_id,
        )
        if len(self.verified_fact_ids) != len(set(self.verified_fact_ids)):
            raise ValueError("verified_fact_ids must be unique")
        if len(self.evidence_ref_ids) != len(set(self.evidence_ref_ids)):
            raise ValueError("evidence_ref_ids must be unique")
        return self


class RuleApprovalDecisionSchemaV08(Phase9BContractModel):
    rule_approval_decision_id: EntityId
    rule_candidate_id: EntityId
    decision: RuleApprovalDecisionValue
    approver_identity: NonEmptyString
    approval_method: RuleApprovalMethod
    reason_code: NonEmptyString
    decided_at: Instant
    policy_version: NonEmptyString


class UnitRuleSetSchemaV08(Phase9BContractModel):
    unit_rule_set_id: EntityId
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    opportunity_unit_id: EntityId
    opportunity_unit_version_id: EntityId
    rule_candidate_id: EntityId
    rule_schema_version: Literal["0.8.0"]
    payload: ProposedRulePayloadSchemaV08
    review_status: Literal["APPROVED"]
    activation_status: Literal["DORMANT"]
    rule_approval_decision_id: EntityId
    created_at: Instant


class HtmlElementSpanLocatorSchemaV08(Phase9BContractModel):
    kind: Literal["html_element_span"]
    selector: NonEmptyString
    text_start: Annotated[int, Field(ge=0)]
    text_end: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def require_span(self) -> Self:
        if self.text_end <= self.text_start:
            raise ValueError("text_end must be after text_start")
        return self


class PdfTextSpanLocatorSchemaV08(Phase9BContractModel):
    kind: Literal["pdf_text_span"]
    page_number: Annotated[int, Field(ge=1)]
    text_start: Annotated[int, Field(ge=0)]
    text_end: Annotated[int, Field(gt=0)]

    @model_validator(mode="after")
    def require_span(self) -> Self:
        if self.text_end <= self.text_start:
            raise ValueError("text_end must be after text_start")
        return self


class PdfTableCellLocatorSchemaV08(Phase9BContractModel):
    kind: Literal["pdf_table_cell"]
    page_number: Annotated[int, Field(ge=1)]
    row_index: Annotated[int, Field(ge=1)]
    column_index: Annotated[int, Field(ge=1)]


class SpreadsheetCellLocatorSchemaV08(Phase9BContractModel):
    kind: Literal["spreadsheet_cell"]
    sheet_name: NonEmptyString
    row: Annotated[int, Field(ge=1)]
    column: Annotated[int, Field(ge=1)]


class SpreadsheetRangeBlockLocatorSchemaV08(Phase9BContractModel):
    kind: Literal["spreadsheet_range"]
    sheet_name: NonEmptyString
    start_row: Annotated[int, Field(ge=1)]
    end_row: Annotated[int, Field(ge=1)]
    start_column: Annotated[int, Field(ge=1)]
    end_column: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def require_range(self) -> Self:
        if self.end_row < self.start_row or self.end_column < self.start_column:
            raise ValueError("range end must not precede start")
        return self


class DocxParagraphLocatorSchemaV08(Phase9BContractModel):
    kind: Literal["docx_paragraph"]
    body_index: Annotated[int, Field(ge=1)]
    paragraph_index: Annotated[int, Field(ge=1)]


class DocxTableCellLocatorSchemaV08(Phase9BContractModel):
    kind: Literal["docx_table_cell"]
    body_index: Annotated[int, Field(ge=1)]
    table_index: Annotated[int, Field(ge=1)]
    row_index: Annotated[int, Field(ge=1)]
    column_index: Annotated[int, Field(ge=1)]


class OpaqueWholeFileLocatorSchemaV08(Phase9BContractModel):
    """Locator for a block that cites an excluded binary as a whole, without any text."""

    kind: Literal["opaque_whole_file"]
    value_sha256: Sha256
    byte_size: Annotated[int, Field(ge=0)]


DocumentBlockLocatorSchemaV08 = Annotated[
    HtmlElementSpanLocatorSchemaV08
    | PdfTextSpanLocatorSchemaV08
    | PdfTableCellLocatorSchemaV08
    | SpreadsheetCellLocatorSchemaV08
    | SpreadsheetRangeBlockLocatorSchemaV08
    | DocxParagraphLocatorSchemaV08
    | DocxTableCellLocatorSchemaV08
    | OpaqueWholeFileLocatorSchemaV08,
    Field(discriminator="kind"),
]


class DocumentBlockSchemaV08(Phase9BContractModel):
    block_id: EntityId
    document_id: EntityId
    artifact_id: EntityId
    document_parse_key: Sha256
    ordinal: Annotated[int, Field(ge=1)]
    block_type: DocumentBlockType
    canonical_text_or_value: NonEmptyString
    structural_locator: DocumentBlockLocatorSchemaV08
    block_hash: Sha256
    evidence_binding_hash: Sha256
    evidence_ref_id: EntityId
    parent_block_id: EntityId | None
    parser_name: NonEmptyString
    parser_version: NonEmptyString
    parse_contract_version: NonEmptyString
    created_at: Instant

    @model_validator(mode="after")
    def require_locator_matches_block_type(self) -> Self:
        expected = {
            DocumentBlockType.HTML_SECTION: "html_element_span",
            DocumentBlockType.HTML_ELEMENT: "html_element_span",
            DocumentBlockType.PDF_TEXT_SPAN: "pdf_text_span",
            DocumentBlockType.PDF_TABLE_CELL: "pdf_table_cell",
            DocumentBlockType.SPREADSHEET_CELL: "spreadsheet_cell",
            DocumentBlockType.SPREADSHEET_RANGE: "spreadsheet_range",
            DocumentBlockType.DOCX_PARAGRAPH: "docx_paragraph",
            DocumentBlockType.DOCX_TABLE_CELL: "docx_table_cell",
        }.get(self.block_type)
        if expected is None or self.structural_locator.kind != expected:
            raise ValueError("DocumentBlock locator kind does not match block type")
        return self


UnitPublicId = Annotated[str, StringConstraints(pattern=r"^unit_[0-9a-f]{32}$")]
NormalizedKey = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class DocumentParseIdentitySchemaV08(Phase9BContractModel):
    artifact_id: EntityId
    artifact_sha256: Sha256
    parser_name: NonEmptyString
    parser_version: NonEmptyString
    parse_contract_version: NonEmptyString
    document_parse_key: Sha256

    @model_validator(mode="after")
    def require_matching_key(self) -> Self:
        expected = document_parse_key(
            artifact_id=self.artifact_id,
            artifact_sha256=self.artifact_sha256,
            parser_name=self.parser_name,
            parser_version=self.parser_version,
            parse_contract_version=self.parse_contract_version,
        )
        if self.document_parse_key != expected:
            raise ValueError("document_parse_key does not match the frozen hash contract")
        return self


class OpportunityUnitSchemaV08(Phase9BContractModel):
    opportunity_unit_id: EntityId
    public_id: UnitPublicId
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    current_unit_key: NonEmptyString
    normalized_current_unit_key: NormalizedKey
    unit_kind: OpportunityUnitKind
    lifecycle_status: OpportunityUnitLifecycleStatus
    current_version_id: EntityId | None
    created_at: Instant
    retired_at: Instant | None

    @model_validator(mode="after")
    def require_lifecycle_shape(self) -> Self:
        if (self.lifecycle_status == OpportunityUnitLifecycleStatus.RETIRED) != (
            self.retired_at is not None
        ):
            raise ValueError("retired_at must be present exactly when lifecycle status is RETIRED")
        return self


class OpportunityUnitVersionSchemaV08(Phase9BContractModel):
    opportunity_unit_version_id: EntityId
    opportunity_unit_id: EntityId
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    version: VersionNumber
    source_bundle_revision_id: EntityId
    effective_from: Instant
    effective_to: Instant | None
    status: OpportunityUnitVersionStatus
    canonical_label: NonEmptyString
    identity_fingerprint: Sha256
    supersedes_version_id: EntityId | None
    created_at: Instant

    @model_validator(mode="after")
    def require_effective_window(self) -> Self:
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        return self


class OpportunityUnitAliasSchemaV08(Phase9BContractModel):
    alias_id: EntityId
    opportunity_id: EntityId
    opportunity_unit_id: EntityId
    normalized_alias_key: NormalizedKey
    display_alias_key: NonEmptyString
    alias_kind: OpportunityUnitAliasKind
    valid_from: Instant
    valid_to: Instant | None
    evidence_ref_id: EntityId
    source_bundle_revision_id: EntityId
    created_at: Instant

    @model_validator(mode="after")
    def require_effective_window(self) -> Self:
        if self.valid_to is not None and self.valid_to <= self.valid_from:
            raise ValueError("valid_to must be after valid_from")
        return self


class OpportunityUnitLineageMemberSchemaV08(Phase9BContractModel):
    member_role: OpportunityUnitLineageMemberRole
    opportunity_unit_id: EntityId
    opportunity_unit_version_id: EntityId


class OpportunityUnitLineageEventSchemaV08(Phase9BContractModel):
    lineage_event_id: EntityId
    opportunity_id: EntityId
    event_type: OpportunityUnitLineageEventType
    reverses_event_id: EntityId | None
    source_bundle_revision_id: EntityId
    evidence_ref_ids: list[EntityId] = Field(min_length=1)
    reason_code: NonEmptyString
    actor_identity: NonEmptyString
    members: list[OpportunityUnitLineageMemberSchemaV08] = Field(min_length=2)
    created_at: Instant

    @model_validator(mode="after")
    def require_event_shape(self) -> Self:
        if (self.event_type == OpportunityUnitLineageEventType.REVERSAL) != (
            self.reverses_event_id is not None
        ):
            raise ValueError("only REVERSAL requires reverses_event_id")
        roles = [member.member_role for member in self.members]
        if (
            OpportunityUnitLineageMemberRole.SOURCE not in roles
            or OpportunityUnitLineageMemberRole.TARGET not in roles
        ):
            raise ValueError("lineage event requires SOURCE and TARGET members")
        return self


class SourceBundleMemberProvenanceSchemaV08(Phase9BContractModel):
    source_bundle_member_id: EntityId
    source_bundle_revision_id: EntityId
    source_id: EntityId
    endpoint_id: EntityId
    capture_observation_id: EntityId
    acquisition_evaluation_id: EntityId
    acquisition_validation_status: str
    acquisition_run_id: EntityId
    recipe_id: EntityId
    recipe_version: NonEmptyString
    policy_version: NonEmptyString
    fetch_strategy: NonEmptyString
    fetcher_name: NonEmptyString
    fetcher_version: NonEmptyString
    validator_name: NonEmptyString
    validator_version: NonEmptyString
    raw_artifact_id: EntityId
    raw_artifact_sha256: Sha256
    raw_artifact_size: Annotated[int, Field(gt=0)]
    storage_bucket: NonEmptyString
    object_key: NonEmptyString
    document_id: EntityId
    document_parse_identity: DocumentParseIdentitySchemaV08
    member_role: SourceBundleMemberRole
    relation_type: SourceBundleRelationType
    precedence: Annotated[int, Field(ge=0, le=1000)]
    related_member_id: EntityId | None
    effective_from: Instant | None
    effective_to: Instant | None
    member_provenance_hash: Sha256

    @model_validator(mode="after")
    def require_exact_lineage(self) -> Self:
        if self.acquisition_validation_status != "VALID":
            raise ValueError("acquisition_validation_status must be VALID")
        if self.document_parse_identity.artifact_id != self.raw_artifact_id:
            raise ValueError("document parse artifact must match raw artifact")
        if self.document_parse_identity.artifact_sha256 != self.raw_artifact_sha256:
            raise ValueError("document parse hash must match raw artifact")
        if (self.relation_type == SourceBundleRelationType.PRIMARY) != (
            self.related_member_id is None
        ):
            raise ValueError("PRIMARY alone has no related member")
        if self.effective_to is not None and (
            self.effective_from is None or self.effective_to <= self.effective_from
        ):
            raise ValueError("effective_to requires an earlier effective_from")
        return self


class SourceBundleRevisionSchemaV08(Phase9BContractModel):
    source_bundle_revision_id: EntityId
    source_bundle_id: EntityId
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    revision_number: VersionNumber
    canonical_bundle_hash: Sha256
    relation_graph_version: NonEmptyString
    precedence_graph_version: NonEmptyString
    effective_as_of: Instant
    status: SourceBundleRevisionStatus
    members: list[SourceBundleMemberProvenanceSchemaV08] = Field(min_length=1)
    created_at: Instant
    frozen_at: Instant | None

    @model_validator(mode="after")
    def require_revision_shape(self) -> Self:
        if (self.status != SourceBundleRevisionStatus.DRAFT) != (self.frozen_at is not None):
            raise ValueError("frozen_at is absent only for a DRAFT revision")
        if any(
            member.source_bundle_revision_id != self.source_bundle_revision_id
            for member in self.members
        ):
            raise ValueError("all members must belong to the same revision")
        return self


class DatasetManifestEntrySchemaV08(Phase9BContractModel):
    entry_id: NonEmptyString
    partition: DatasetPartition
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    opportunity_unit_id: EntityId
    opportunity_unit_version_id: EntityId
    source_bundle_id: EntityId
    source_bundle_revision_id: EntityId
    canonical_bundle_hash: Sha256
    atomic_group_id: NonEmptyString
    near_duplicate_cluster_ids: list[NonEmptyString]
    unit_lineage_ids: list[NonEmptyString]
    evaluation_as_of: Instant
    answer_access_class: AnswerAccessClass


_PARTITION_COUNTS = {
    DatasetPartition.CALIBRATION: 30,
    DatasetPartition.DEVELOPMENT: 70,
    DatasetPartition.VALIDATION: 30,
    DatasetPartition.LOCKED_ACCEPTANCE: 200,
}
_PARTITION_ACCESS = {
    DatasetPartition.CALIBRATION: AnswerAccessClass.ASSISTED_CALIBRATION,
    DatasetPartition.DEVELOPMENT: AnswerAccessClass.DEVELOPMENT_VISIBLE,
    DatasetPartition.VALIDATION: AnswerAccessClass.VALIDATION_BLIND,
    DatasetPartition.LOCKED_ACCEPTANCE: AnswerAccessClass.LOCKED_BLIND,
}


class DatasetManifestSchemaV08(Phase9BContractModel):
    split_manifest_version: NonEmptyString
    partition: DatasetPartition
    expected_entry_count: Annotated[int, Field(gt=0)]
    actual_entry_count: Annotated[int, Field(gt=0)]
    atomic_group_count: Annotated[int, Field(gt=0)]
    entries: list[DatasetManifestEntrySchemaV08] = Field(min_length=1)
    evaluation_cutoff: Instant
    answer_access_class: AnswerAccessClass
    frozen_by: NonEmptyString
    frozen_at: Instant
    invalidated_at: Instant | None
    invalidation_reason: NonEmptyString | None
    successor_manifest_hash: Sha256 | None
    manifest_hash: Sha256

    @model_validator(mode="after")
    def require_exact_partition(self) -> Self:
        exact = _PARTITION_COUNTS[self.partition]
        if self.expected_entry_count != exact or self.actual_entry_count != exact:
            raise ValueError(f"partition requires exact entry count {exact}")
        if len(self.entries) != exact:
            raise ValueError(f"entries must contain the exact entry count {exact}")
        if any(entry.partition != self.partition for entry in self.entries):
            raise ValueError("every entry must use the manifest partition")
        expected_access = _PARTITION_ACCESS[self.partition]
        if self.answer_access_class != expected_access or any(
            entry.answer_access_class != expected_access for entry in self.entries
        ):
            raise ValueError("answer access must match the partition")
        distinct_groups = {entry.atomic_group_id for entry in self.entries}
        if self.atomic_group_count != len(distinct_groups):
            raise ValueError("atomic_group_count must equal the distinct group count")
        invalidated = self.invalidated_at is not None
        if invalidated != (self.invalidation_reason is not None):
            raise ValueError("invalidation timestamp and reason must be paired")
        if self.successor_manifest_hash is not None and not invalidated:
            raise ValueError("successor requires an invalidated manifest")
        return self


class GoldFieldJudgmentSchemaV08(Phase9BContractModel):
    field_name: NonEmptyString
    gold_state: GoldFieldState
    normalized_value: JsonValue | None
    evidence_block_ids: list[EntityId]
    high_impact: bool
    precedence_sensitive: bool

    @model_validator(mode="after")
    def require_state_shape(self) -> Self:
        if (self.gold_state == GoldFieldState.KNOWN_SUPPORTED) != (
            self.normalized_value is not None
        ):
            raise ValueError("normalized_value is required only for KNOWN_SUPPORTED")
        if self.gold_state == GoldFieldState.KNOWN_SUPPORTED and not self.evidence_block_ids:
            raise ValueError("KNOWN_SUPPORTED requires field-level evidence")
        return self


class GoldAnnotationTaskSchemaV08(Phase9BContractModel):
    gold_annotation_task_id: EntityId
    dataset_manifest_id: EntityId
    entry_id: NonEmptyString
    partition: DatasetPartition
    answer_access_class: AnswerAccessClass
    annotator_identity: NonEmptyString
    verifier_identity: NonEmptyString
    adjudicator_identity: NonEmptyString
    curator_identity: NonEmptyString
    role_attestation_references: dict[GoldReviewRole, NonEmptyString]
    blind_started_at: Instant
    blind_ended_at: Instant | None
    split_seed_reference: NonEmptyString
    status: Literal["BLIND_REVIEW", "READY_FOR_ADJUDICATION", "FROZEN", "INVALIDATED"]
    created_at: Instant

    @model_validator(mode="after")
    def require_independent_human_roles(self) -> Self:
        identities = {
            self.annotator_identity,
            self.verifier_identity,
            self.adjudicator_identity,
            self.curator_identity,
        }
        if len(identities) != 4:
            raise ValueError("Gold responsibility identities must be distinct")
        if any(not identity.startswith("human:") for identity in identities):
            raise ValueError("each Gold role requires an explicit human responsibility identity")
        if set(self.role_attestation_references) != set(GoldReviewRole):
            raise ValueError("each Gold role requires an identity attestation reference")
        expected_access = _PARTITION_ACCESS[self.partition]
        if self.answer_access_class != expected_access:
            raise ValueError("answer access must match the partition")
        if (self.blind_ended_at is None) != (self.status == "BLIND_REVIEW"):
            raise ValueError("blind_ended_at is absent exactly during BLIND_REVIEW")
        return self


class GoldRoleAttestationSchemaV08(Phase9BContractModel):
    gold_role_attestation_id: EntityId
    review_role: GoldReviewRole
    subject_identity: NonEmptyString
    attestation_authority_identity: NonEmptyString
    verification_method: Literal[
        "EXTERNAL_HUMAN_DIRECTORY",
        "SIGNED_ACCOUNT_ASSERTION",
        "IN_PERSON_ACCOUNTABILITY_RECORD",
    ]
    external_evidence_reference: NonEmptyString
    external_evidence_sha256: Sha256
    verified_at: Instant
    expires_at: Instant | None
    created_at: Instant

    @model_validator(mode="after")
    def require_external_human_attestation(self) -> Self:
        if not self.subject_identity.startswith("human:"):
            raise ValueError("Gold attestation subject must be a human responsibility identity")
        if self.attestation_authority_identity == self.subject_identity:
            raise ValueError("Gold attestation authority must be independent from its subject")
        if self.external_evidence_reference.startswith(
            ("synthetic:", "synthetic-fixture:", "claimed-human:")
        ):
            raise ValueError("Gold human attestation requires external evidence")
        if self.expires_at is not None and self.expires_at <= self.verified_at:
            raise ValueError("Gold human attestation expiry must follow verification")
        return self


class GoldAnnotationSubmissionSchemaV08(Phase9BContractModel):
    gold_annotation_submission_id: EntityId
    gold_annotation_task_id: EntityId
    review_role: GoldReviewRole
    actor_identity: NonEmptyString
    assisted_calibration: bool
    judgments: list[GoldFieldJudgmentSchemaV08] = Field(min_length=1)
    submitted_at: Instant

    @field_validator("review_role")
    @classmethod
    def require_submission_role(cls, value: GoldReviewRole) -> GoldReviewRole:
        if value not in {GoldReviewRole.ANNOTATOR, GoldReviewRole.VERIFIER}:
            raise ValueError("only ANNOTATOR and VERIFIER submit independent reviews")
        return value

    @field_validator("judgments")
    @classmethod
    def require_unique_fields(
        cls, value: list[GoldFieldJudgmentSchemaV08]
    ) -> list[GoldFieldJudgmentSchemaV08]:
        fields = [item.field_name for item in value]
        if len(fields) != len(set(fields)):
            raise ValueError("each submission may judge a field only once")
        return value


class GoldAdjudicationDecisionSchemaV08(Phase9BContractModel):
    gold_adjudication_decision_id: EntityId
    gold_annotation_task_id: EntityId
    annotation_submission_id: EntityId
    verification_submission_id: EntityId
    adjudicator_identity: NonEmptyString
    judgments: list[GoldFieldJudgmentSchemaV08] = Field(min_length=1)
    reason_code: NonEmptyString
    decided_at: Instant


class GoldTruthVersionSchemaV08(Phase9BContractModel):
    gold_truth_version_id: EntityId
    gold_annotation_task_id: EntityId
    version: VersionNumber
    supersedes_truth_version_id: EntityId | None = None
    revision_reason_code: NonEmptyString = "INITIAL_FREEZE"
    source_submission_ids: list[EntityId] = Field(min_length=2, max_length=2)
    adjudication_decision_id: EntityId | None
    curator_identity: NonEmptyString
    judgments: list[GoldFieldJudgmentSchemaV08] = Field(min_length=1)
    truth_hash: Sha256
    frozen_at: Instant

    @field_validator("source_submission_ids")
    @classmethod
    def require_distinct_submissions(cls, value: list[EntityId]) -> list[EntityId]:
        if len(set(value)) != 2:
            raise ValueError("Gold truth requires two distinct independent submissions")
        return value

    @model_validator(mode="after")
    def require_version_chain(self) -> Self:
        if (self.version == 1) != (self.supersedes_truth_version_id is None):
            raise ValueError("only Gold truth version 1 has no predecessor")
        return self


class RawResponseReferenceSchemaV08(Phase9BContractModel):
    kind: RawResponseReferenceKind
    storage_bucket: LedgerStorageBucket | None
    object_key: LedgerObjectKey | None
    content_sha256: Sha256 | None
    provider_response_id: LedgerProviderResponseId | None

    @model_validator(mode="after")
    def require_exact_reference_shape(self) -> Self:
        internal = self.kind is RawResponseReferenceKind.INTERNAL_OBJECT
        if internal != (
            self.storage_bucket is not None
            and self.object_key is not None
            and self.content_sha256 is not None
        ):
            raise ValueError("internal response references require bucket, object key and hash")
        if internal == (self.provider_response_id is not None):
            raise ValueError("response reference kind and provider response ID disagree")
        if self.object_key is not None and (
            "://" in self.object_key or self.object_key.startswith(("/", "\\"))
        ):
            raise ValueError("raw response object key must be an internal relative object key")
        return self


class ModelCallIntentSchemaV08(Phase9BContractModel):
    model_call_id: EntityId
    task_spec_name: LedgerIdentifier64
    task_spec_version: LedgerIdentifier32
    provider: LedgerIdentifier64
    model_id: LedgerIdentifier128
    model_snapshot: LedgerIdentifier128
    adapter_name: LedgerIdentifier64
    adapter_version: LedgerIdentifier32
    runtime_version: LedgerIdentifier64
    canonical_request_hash: Sha256
    canonical_message_hashes: list[Sha256] = Field(min_length=1)
    input_block_ids: list[EntityId] = Field(min_length=1)
    input_block_hashes: list[Sha256] = Field(min_length=1)
    source_bundle_revision_id: EntityId
    target_scope: ExtractionTargetScope
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    opportunity_unit_id: EntityId | None
    opportunity_unit_version_id: EntityId | None
    unit_segmentation_version: LedgerIdentifier64 | None
    prompt_version: LedgerIdentifier64
    output_schema_version: LedgerIdentifier64
    parser_version: LedgerIdentifier64
    contract_version: LedgerIdentifier64
    temperature: Annotated[float, Field(strict=True, ge=0, le=2)]
    top_p: Annotated[float, Field(strict=True, ge=0, le=1)]
    seed: int
    egress_decision_id: EntityId
    validation_pipeline_version: LedgerIdentifier64
    retention_class: RetentionClass
    registered_at: Instant

    @model_validator(mode="after")
    def require_intent_bindings(self) -> Self:
        if len(self.input_block_ids) != len(self.input_block_hashes):
            raise ValueError("call input block IDs and hashes must align")
        if len(set(self.input_block_ids)) != len(self.input_block_ids):
            raise ValueError("call input block IDs must be unique")
        unit_target = self.target_scope is ExtractionTargetScope.UNIT
        if unit_target != (
            self.opportunity_unit_id is not None and self.opportunity_unit_version_id is not None
        ):
            raise ValueError("UNIT alone requires exact Unit identity")
        if unit_target != (self.unit_segmentation_version is not None):
            raise ValueError("UNIT alone requires a segmentation version")
        return self


class ModelTaskSpecSchemaV08(Phase9BContractModel):
    model_task_spec_id: EntityId
    task_name: LedgerIdentifier64
    task_version: LedgerIdentifier32
    route_class: ModelRouteClass
    allowed_input_block_types: list[DocumentBlockType] = Field(min_length=1)
    output_schema_version: LedgerIdentifier64
    max_input_tokens: Annotated[int, Field(ge=1)]
    max_output_tokens: Annotated[int, Field(ge=1)]
    evidence_required: bool
    abstention_allowed: bool
    risk_class: LedgerIdentifier32
    provider_capabilities: list[LedgerIdentifier128] = Field(min_length=1)
    egress_policy_id: LedgerIdentifier64
    timeout_ms: Annotated[int, Field(ge=100, le=120000)]
    max_attempts: Annotated[int, Field(ge=1, le=3)]
    initial_backoff_ms: Annotated[int, Field(ge=0, le=10000)]
    backoff_multiplier: Annotated[float, Field(strict=True, ge=1, le=4)]
    max_backoff_ms: Annotated[int, Field(ge=0, le=30000)]
    max_concurrency: Annotated[int, Field(ge=1, le=8)]
    max_batch_size: Annotated[int, Field(ge=1, le=16)]
    fallback_policy: Literal["DISABLED"]
    max_fallbacks: Literal[0]
    created_at: Instant

    @model_validator(mode="after")
    def require_task_bounds(self) -> Self:
        if self.max_backoff_ms < self.initial_backoff_ms:
            raise ValueError("maximum backoff must not precede the initial backoff")
        if len(set(self.allowed_input_block_types)) != len(self.allowed_input_block_types):
            raise ValueError("allowed input block types must be unique")
        if len(set(self.provider_capabilities)) != len(self.provider_capabilities):
            raise ValueError("provider capabilities must be unique")
        return self


class EgressBlockClassificationSchemaV08(Phase9BContractModel):
    classification_id: EntityId
    block_id: EntityId
    block_hash: Sha256
    classification_version: LedgerIdentifier64
    classifications: list[LedgerIdentifier128] = Field(min_length=1)
    contains_user_data: bool
    classifier_identity: LedgerIdentifier128
    created_at: Instant

    @field_validator("classifications")
    @classmethod
    def require_unique_classifications(
        cls,
        value: list[LedgerIdentifier128],
    ) -> list[LedgerIdentifier128]:
        if len(set(value)) != len(value):
            raise ValueError("egress classifications must be unique")
        return value


class SourceEgressPolicySnapshotSchemaV08(Phase9BContractModel):
    snapshot_id: LedgerIdentifier64
    snapshot_hash: Sha256
    source_bundle_revision_id: EntityId
    allows_egress: bool
    valid_from: Instant
    valid_until: Instant
    recorded_by: LedgerIdentifier128
    created_at: Instant

    @model_validator(mode="after")
    def require_valid_window(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("source egress policy window must be positive")
        return self


class ProviderEgressPolicySnapshotSchemaV08(Phase9BContractModel):
    snapshot_id: LedgerIdentifier64
    snapshot_hash: Sha256
    provider: LedgerIdentifier64
    region: LedgerIdentifier64
    active: bool
    zero_retention: bool
    training_use: bool
    supports_idempotency: bool
    allowed_classifications: list[LedgerIdentifier128] = Field(min_length=1)
    retention_class: RetentionClass
    valid_from: Instant
    valid_until: Instant
    recorded_by: LedgerIdentifier128
    created_at: Instant

    @model_validator(mode="after")
    def require_provider_policy_shape(self) -> Self:
        if self.valid_until <= self.valid_from:
            raise ValueError("Provider egress policy window must be positive")
        if len(set(self.allowed_classifications)) != len(self.allowed_classifications):
            raise ValueError("allowed egress classifications must be unique")
        return self


class EgressDecisionSchemaV08(Phase9BContractModel):
    egress_decision_id: EntityId
    task_spec_name: LedgerIdentifier64
    task_spec_version: LedgerIdentifier32
    source_bundle_revision_id: EntityId
    target_scope: ExtractionTargetScope
    opportunity_id: EntityId
    opportunity_version: VersionNumber
    opportunity_unit_id: EntityId | None
    opportunity_unit_version_id: EntityId | None
    input_block_ids: list[EntityId] = Field(min_length=1)
    input_block_hashes: list[Sha256] = Field(min_length=1)
    data_classification_version: LedgerIdentifier64
    minimizer_version: LedgerIdentifier64
    redactor_version: LedgerIdentifier64
    source_policy_snapshot_id: LedgerIdentifier64
    source_policy_snapshot_hash: Sha256
    provider_policy_snapshot_id: LedgerIdentifier64
    provider_policy_snapshot_hash: Sha256
    provider: LedgerIdentifier64
    provider_region: LedgerIdentifier64
    original_input_hash: Sha256
    actual_payload_hash: Sha256 | None
    decision: EgressDecisionValue
    actor_type: Literal["SYSTEM", "HUMAN"]
    actor_identity: LedgerIdentifier128 | None
    reason_codes: list[LedgerErrorCode] = Field(min_length=1)
    created_at: Instant
    expires_at: Instant | None

    @model_validator(mode="after")
    def require_decision_bindings(self) -> Self:
        if len(self.input_block_ids) != len(self.input_block_hashes):
            raise ValueError("egress input block IDs and hashes must align")
        if len(set(self.input_block_ids)) != len(self.input_block_ids):
            raise ValueError("egress input block IDs must be unique")
        if len(set(self.reason_codes)) != len(self.reason_codes):
            raise ValueError("egress reason codes must be unique")
        unit_target = self.target_scope is ExtractionTargetScope.UNIT
        if unit_target != (
            self.opportunity_unit_id is not None and self.opportunity_unit_version_id is not None
        ):
            raise ValueError("UNIT alone requires exact Unit identity")
        allowed = self.decision in {
            EgressDecisionValue.ALLOW,
            EgressDecisionValue.REDACT_AND_ALLOW,
        }
        if allowed != (self.actual_payload_hash is not None and self.expires_at is not None):
            raise ValueError("allowed egress requires an exact payload hash and expiry")
        if self.expires_at is not None and self.expires_at <= self.created_at:
            raise ValueError("egress expiry must follow creation")
        if (self.actor_type == "HUMAN") != (self.actor_identity is not None):
            raise ValueError("human egress decisions require an actor identity")
        return self


class ModelAttemptResultSchemaV08(Phase9BContractModel):
    outcome: ModelAttemptOutcome
    provider_http_status: Annotated[int, Field(ge=100, le=599)] | None
    error_code: LedgerErrorCode | None
    raw_response_reference: RawResponseReferenceSchemaV08 | None
    response_hash: Sha256 | None
    parsed_result_hash: Sha256 | None
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    cache_read_tokens: Annotated[int, Field(ge=0)]
    cache_write_tokens: Annotated[int, Field(ge=0)]
    cost_status: Literal["REPORTED", "COST_NOT_REPORTED"]
    monetary_cost: Annotated[float, Field(strict=True, ge=0)] | None
    latency_ms: Annotated[int, Field(ge=0)]
    completed_at: Instant

    @model_validator(mode="after")
    def require_terminal_result_shape(self) -> Self:
        if self.outcome is ModelAttemptOutcome.AUTHORITY_REJECTED:
            raise ValueError("authorization rejection is database-derived, not a Provider result")
        reported = self.cost_status == "REPORTED"
        if reported != (self.monetary_cost is not None):
            raise ValueError("cost status and monetary cost must agree")
        succeeded = self.outcome is ModelAttemptOutcome.SUCCEEDED
        if succeeded != (
            self.raw_response_reference is not None
            and self.response_hash is not None
            and self.parsed_result_hash is not None
            and self.error_code is None
        ):
            raise ValueError("attempt success provenance shape is invalid")
        if not succeeded and self.parsed_result_hash is not None:
            raise ValueError("failed attempt cannot bind a parsed result hash")
        return self


class ModelCallAttemptLedgerSchemaV08(Phase9BContractModel):
    attempt: Annotated[int, Field(ge=1, le=3)]
    attempt_id: EntityId
    authorization_decision: Literal["AUTHORIZED", "AUTHORITY_REJECTED"]
    authorization_reason_code: LedgerErrorCode
    authorization_checked_at: Instant
    dispatch_deadline: Instant | None
    provider_invocation_allowed: bool
    outcome: ModelAttemptOutcome | None
    error_code: LedgerErrorCode | None
    provider_http_status: Annotated[int, Field(ge=100, le=599)] | None
    completed_at: Instant | None


class ModelCallLedgerViewSchemaV08(ModelCallIntentSchemaV08):
    status: ModelCallLedgerStatus
    terminal_disposition: ModelTerminalDisposition | None
    terminal_reason_code: LedgerErrorCode | None
    finalized_at: Instant | None
    attempt_count: Annotated[int, Field(ge=0, le=3)]
    retry_count: Annotated[int, Field(ge=0, le=2)]
    fallback_count: Literal[0]
    attempts: list[ModelCallAttemptLedgerSchemaV08]
    provider_response_id: LedgerProviderResponseId | None
    raw_response_reference_kind: RawResponseReferenceKind | None
    raw_response_storage_bucket: LedgerStorageBucket | None
    raw_response_object_key: LedgerObjectKey | None
    raw_response_sha256: Sha256 | None
    response_hash: Sha256 | None
    parsed_result_hash: Sha256 | None
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    cache_read_tokens: Annotated[int, Field(ge=0)]
    cache_write_tokens: Annotated[int, Field(ge=0)]
    monetary_cost: Annotated[Decimal, Field(ge=0)]
    latency_ms: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def require_derived_ledger_shape(self) -> Self:
        if self.attempt_count != len(self.attempts):
            raise ValueError("attempt_count must be derived from the attempt ledger")
        if self.retry_count != max(self.attempt_count - 1, 0):
            raise ValueError("retry_count must be derived from attempt_count")
        in_progress = self.status is ModelCallLedgerStatus.IN_PROGRESS
        if in_progress != (
            self.terminal_disposition is None
            and self.terminal_reason_code is None
            and self.finalized_at is None
        ):
            raise ValueError("terminal fields must be derived from finalization")
        if self.attempts and any(
            attempt.attempt != index for index, attempt in enumerate(self.attempts, start=1)
        ):
            raise ValueError("attempt ledger must be contiguous and ordered")
        reference = self.raw_response_reference_kind
        if reference is None:
            if any(
                value is not None
                for value in (
                    self.provider_response_id,
                    self.raw_response_storage_bucket,
                    self.raw_response_object_key,
                    self.raw_response_sha256,
                )
            ):
                raise ValueError("flattened response reference is incomplete")
        elif reference is RawResponseReferenceKind.PROVIDER_RESPONSE_ID:
            if self.provider_response_id is None or any(
                value is not None
                for value in (
                    self.raw_response_storage_bucket,
                    self.raw_response_object_key,
                    self.raw_response_sha256,
                )
            ):
                raise ValueError("Provider response reference is incomplete")
        elif self.provider_response_id is not None or any(
            value is None
            for value in (
                self.raw_response_storage_bucket,
                self.raw_response_object_key,
                self.raw_response_sha256,
            )
        ):
            raise ValueError("internal response reference is incomplete")
        return self


__all__ = [
    "AnswerAccessClass",
    "DatasetManifestEntrySchemaV08",
    "DatasetManifestSchemaV08",
    "DatasetPartition",
    "DocumentBlockLocatorSchemaV08",
    "DocumentBlockSchemaV08",
    "DocumentBlockType",
    "DocumentParseIdentitySchemaV08",
    "EgressBlockClassificationSchemaV08",
    "EgressDecisionSchemaV08",
    "EgressDecisionValue",
    "EvidenceSupportResult",
    "ExtractionCandidateSchemaV08",
    "ExtractionRunSchemaV08",
    "ExtractionRunStatus",
    "ExtractionTargetScope",
    "ExtractorKind",
    "OpaqueWholeFileLocatorSchemaV08",
    "FactVerificationDecision",
    "FactVerificationDecisionSchemaV08",
    "GoldAnnotationSubmissionSchemaV08",
    "GoldAnnotationTaskSchemaV08",
    "GoldAdjudicationDecisionSchemaV08",
    "GoldFieldJudgmentSchemaV08",
    "GoldFieldState",
    "GoldReviewRole",
    "GoldRoleAttestationSchemaV08",
    "GoldTruthVersionSchemaV08",
    "ModelAttemptOutcome",
    "ModelAttemptResultSchemaV08",
    "ModelCallFinalStatus",
    "ModelCallAttemptLedgerSchemaV08",
    "ModelCallIntentSchemaV08",
    "ModelCallLedgerStatus",
    "ModelCallLedgerViewSchemaV08",
    "ModelRouteClass",
    "ModelTaskSpecSchemaV08",
    "ModelTerminalDisposition",
    "OpportunityUnitAliasKind",
    "OpportunityUnitAliasSchemaV08",
    "OpportunityUnitKind",
    "OpportunityUnitLifecycleStatus",
    "OpportunityUnitLineageEventSchemaV08",
    "OpportunityUnitVersionSchemaV08",
    "OpportunityUnitSchemaV08",
    "PrecedenceCheckResult",
    "ProviderEgressPolicySnapshotSchemaV08",
    "PredictionFieldState",
    "RawResponseReferenceKind",
    "RawResponseReferenceSchemaV08",
    "RetentionClass",
    "ProposedRulePayloadSchemaV08",
    "RuleApprovalDecisionSchemaV08",
    "RuleApprovalDecisionValue",
    "RuleApprovalMethod",
    "RuleCandidateSchemaV08",
    "RuleCandidateStatus",
    "SourceBundleMemberProvenanceSchemaV08",
    "SourceBundleRevisionSchemaV08",
    "SourceEgressPolicySnapshotSchemaV08",
    "UnitRuleSetSchemaV08",
    "VerificationMethod",
    "VerifiedFactSchemaV08",
    "VerifiedFactSetStatus",
    "VerifiedFactState",
    "VersionedVerifiedFactSetSchemaV08",
]

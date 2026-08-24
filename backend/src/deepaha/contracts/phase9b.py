from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, StringConstraints, model_validator

from deepaha.contracts.common import EntityId, Instant, NonEmptyString, Sha256, VersionNumber
from deepaha.contracts.phase1 import ContractModel
from deepaha.p9b.hashing import document_parse_key


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


DocumentBlockLocatorSchemaV08 = Annotated[
    HtmlElementSpanLocatorSchemaV08
    | PdfTextSpanLocatorSchemaV08
    | PdfTableCellLocatorSchemaV08
    | SpreadsheetCellLocatorSchemaV08
    | SpreadsheetRangeBlockLocatorSchemaV08
    | DocxParagraphLocatorSchemaV08
    | DocxTableCellLocatorSchemaV08,
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


__all__ = [
    "AnswerAccessClass",
    "DatasetManifestEntrySchemaV08",
    "DatasetManifestSchemaV08",
    "DatasetPartition",
    "DocumentBlockLocatorSchemaV08",
    "DocumentBlockSchemaV08",
    "DocumentBlockType",
    "DocumentParseIdentitySchemaV08",
    "OpportunityUnitAliasKind",
    "OpportunityUnitAliasSchemaV08",
    "OpportunityUnitKind",
    "OpportunityUnitLifecycleStatus",
    "OpportunityUnitLineageEventSchemaV08",
    "OpportunityUnitVersionSchemaV08",
    "OpportunityUnitSchemaV08",
    "SourceBundleMemberProvenanceSchemaV08",
    "SourceBundleRevisionSchemaV08",
]

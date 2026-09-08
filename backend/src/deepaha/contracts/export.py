import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from deepaha.contracts.evidence_anchor import ReaderAnchor
from deepaha.contracts.phase1 import (
    DocumentSchema,
    EvidenceRefSchema,
    OpportunitySchema,
    RawArtifactSchema,
    SourceSchema,
)
from deepaha.contracts.phase2 import (
    CaptureObservationSchema,
    EvidenceRefSchemaV02,
    OpportunitySchemaV02,
    ParseAttemptSchema,
    SourceEndpointSchema,
)
from deepaha.contracts.phase3 import (
    DocumentOpportunityLinkSchema,
    OpportunityAliasSchemaV03,
    OpportunityEventSchemaV03,
    OpportunityIdentityActionSchema,
    OpportunityResolutionCandidateSchema,
    OpportunityVersionSchemaV03,
)
from deepaha.contracts.phase4 import (
    EligibilityResultSchemaV04,
    EvaluationRunSchemaV04,
    MatchSnapshotSchemaV04,
    ProfileSnapshotSchemaV04,
    RuleEvidenceSchemaV04,
    RuleSchemaV04,
    RuleSetSchemaV04,
)
from deepaha.contracts.phase6 import (
    PersonalActionEventSchemaV05,
    PersonalActionSnapshotSchemaV05,
    PersonalRankingSnapshotSchemaV05,
    UserStateSnapshotSchemaV05,
)
from deepaha.contracts.phase7 import (
    ApprovedFeedbackLabelSchemaV06,
    FeedbackAdjudicationSchemaV06,
    FeedbackConfidenceAssessmentSchemaV06,
    FeedbackEventSchemaV06,
    FeedbackEvidenceLinkSchemaV06,
    FeedbackReviewCaseSnapshotSchemaV06,
    ImprovementCandidateSchemaV06,
    OfflineEvaluationCandidateSchemaV06,
    ReleaseGateDecisionSchemaV06,
    ShadowTestCandidateSchemaV06,
    ValidationRunSchemaV06,
)
from deepaha.contracts.phase8 import (
    DeadlineChangeReminderIntentSchemaV07,
    NotificationDeliveryAttemptSchemaV07,
    ReminderPreferenceSnapshotSchemaV07,
    TestInboxEntrySchemaV07,
)
from deepaha.contracts.phase9b import (
    DatasetManifestSchemaV08,
    DocumentBlockSchemaV08,
    DocumentParseIdentitySchemaV08,
    EgressBlockClassificationSchemaV08,
    EgressDecisionSchemaV08,
    ExtractionCandidateSchemaV08,
    ExtractionRunSchemaV08,
    FactVerificationDecisionSchemaV08,
    GoldAdjudicationDecisionSchemaV08,
    GoldAnnotationSubmissionSchemaV08,
    GoldAnnotationTaskSchemaV08,
    GoldRoleAttestationSchemaV08,
    GoldTruthVersionSchemaV08,
    ModelAttemptResultSchemaV08,
    ModelCallIntentSchemaV08,
    ModelCallLedgerViewSchemaV08,
    ModelTaskSpecSchemaV08,
    OpportunityUnitAliasSchemaV08,
    OpportunityUnitLineageEventSchemaV08,
    OpportunityUnitSchemaV08,
    OpportunityUnitVersionSchemaV08,
    ProviderEgressPolicySnapshotSchemaV08,
    RuleApprovalDecisionSchemaV08,
    RuleCandidateSchemaV08,
    SourceBundleMemberProvenanceSchemaV08,
    SourceBundleRevisionSchemaV08,
    SourceEgressPolicySnapshotSchemaV08,
    UnitRuleSetSchemaV08,
    VerifiedFactSchemaV08,
    VersionedVerifiedFactSetSchemaV08,
)

PHASE1_SCHEMAS: dict[str, type[BaseModel]] = {
    "source.schema.json": SourceSchema,
    "raw-artifact.schema.json": RawArtifactSchema,
    "document.schema.json": DocumentSchema,
    "opportunity.schema.json": OpportunitySchema,
    "evidence-ref.schema.json": EvidenceRefSchema,
}

PHASE2_SCHEMAS: dict[str, type[BaseModel]] = {
    "source.schema.json": SourceSchema,
    "source-endpoint.schema.json": SourceEndpointSchema,
    "capture-observation.schema.json": CaptureObservationSchema,
    "raw-artifact.schema.json": RawArtifactSchema,
    "document.schema.json": DocumentSchema,
    "parse-attempt.schema.json": ParseAttemptSchema,
    "opportunity.schema.json": OpportunitySchemaV02,
    "evidence-ref.schema.json": EvidenceRefSchemaV02,
}

PHASE3_SCHEMAS: dict[str, type[BaseModel]] = dict(PHASE2_SCHEMAS)
PHASE3_SCHEMAS.update(
    {
        "opportunity-version.schema.json": OpportunityVersionSchemaV03,
        "opportunity-event.schema.json": OpportunityEventSchemaV03,
        "document-opportunity-link.schema.json": DocumentOpportunityLinkSchema,
        "opportunity-resolution-candidate.schema.json": OpportunityResolutionCandidateSchema,
        "opportunity-alias.schema.json": OpportunityAliasSchemaV03,
        "opportunity-identity-action.schema.json": OpportunityIdentityActionSchema,
    }
)

PHASE4_SCHEMAS: dict[str, type[BaseModel]] = dict(PHASE3_SCHEMAS)
PHASE4_SCHEMAS.update(
    {
        "rule-set.schema.json": RuleSetSchemaV04,
        "rule.schema.json": RuleSchemaV04,
        "rule-evidence.schema.json": RuleEvidenceSchemaV04,
        "profile-snapshot.schema.json": ProfileSnapshotSchemaV04,
        "eligibility-result.schema.json": EligibilityResultSchemaV04,
        "match-snapshot.schema.json": MatchSnapshotSchemaV04,
        "evaluation-run.schema.json": EvaluationRunSchemaV04,
    }
)

PHASE6_SCHEMAS: dict[str, type[BaseModel]] = dict(PHASE4_SCHEMAS)
PHASE6_SCHEMAS.update(
    {
        "user-state-snapshot.schema.json": UserStateSnapshotSchemaV05,
        "personal-ranking-snapshot.schema.json": PersonalRankingSnapshotSchemaV05,
        "personal-action-snapshot.schema.json": PersonalActionSnapshotSchemaV05,
        "personal-action-event.schema.json": PersonalActionEventSchemaV05,
    }
)

PHASE7_SCHEMAS: dict[str, type[BaseModel]] = {
    "feedback-event.schema.json": FeedbackEventSchemaV06,
    "feedback-evidence-link.schema.json": FeedbackEvidenceLinkSchemaV06,
    "feedback-review-case-snapshot.schema.json": FeedbackReviewCaseSnapshotSchemaV06,
    "feedback-confidence-assessment.schema.json": FeedbackConfidenceAssessmentSchemaV06,
    "feedback-adjudication.schema.json": FeedbackAdjudicationSchemaV06,
    "approved-feedback-label.schema.json": ApprovedFeedbackLabelSchemaV06,
    "improvement-candidate.schema.json": ImprovementCandidateSchemaV06,
    "offline-evaluation-candidate.schema.json": OfflineEvaluationCandidateSchemaV06,
    "shadow-test-candidate.schema.json": ShadowTestCandidateSchemaV06,
    "validation-run.schema.json": ValidationRunSchemaV06,
    "release-gate-decision.schema.json": ReleaseGateDecisionSchemaV06,
}

PHASE8_SCHEMAS: dict[str, type[BaseModel]] = {
    "reminder-preference-snapshot.schema.json": ReminderPreferenceSnapshotSchemaV07,
    "deadline-change-reminder-intent.schema.json": DeadlineChangeReminderIntentSchemaV07,
    "notification-delivery-attempt.schema.json": NotificationDeliveryAttemptSchemaV07,
    "test-inbox-entry.schema.json": TestInboxEntrySchemaV07,
}

PHASE9B_SCHEMAS: dict[str, type[BaseModel]] = {
    "document-block.schema.json": DocumentBlockSchemaV08,
    "egress-block-classification.schema.json": EgressBlockClassificationSchemaV08,
    "extraction-run.schema.json": ExtractionRunSchemaV08,
    "extraction-candidate.schema.json": ExtractionCandidateSchemaV08,
    "fact-verification-decision.schema.json": FactVerificationDecisionSchemaV08,
    "gold-annotation-task.schema.json": GoldAnnotationTaskSchemaV08,
    "gold-annotation-submission.schema.json": GoldAnnotationSubmissionSchemaV08,
    "gold-adjudication-decision.schema.json": GoldAdjudicationDecisionSchemaV08,
    "gold-role-attestation.schema.json": GoldRoleAttestationSchemaV08,
    "gold-truth-version.schema.json": GoldTruthVersionSchemaV08,
    "egress-decision.schema.json": EgressDecisionSchemaV08,
    "model-attempt-result.schema.json": ModelAttemptResultSchemaV08,
    "model-call-intent.schema.json": ModelCallIntentSchemaV08,
    "model-call-ledger-view.schema.json": ModelCallLedgerViewSchemaV08,
    "model-task-spec.schema.json": ModelTaskSpecSchemaV08,
    "provider-egress-policy-snapshot.schema.json": ProviderEgressPolicySnapshotSchemaV08,
    "verified-fact.schema.json": VerifiedFactSchemaV08,
    "versioned-verified-fact-set.schema.json": VersionedVerifiedFactSetSchemaV08,
    "rule-candidate.schema.json": RuleCandidateSchemaV08,
    "rule-approval-decision.schema.json": RuleApprovalDecisionSchemaV08,
    "unit-rule-set.schema.json": UnitRuleSetSchemaV08,
    "opportunity-unit.schema.json": OpportunityUnitSchemaV08,
    "opportunity-unit-version.schema.json": OpportunityUnitVersionSchemaV08,
    "opportunity-unit-alias.schema.json": OpportunityUnitAliasSchemaV08,
    "opportunity-unit-lineage-event.schema.json": OpportunityUnitLineageEventSchemaV08,
    "document-parse-identity.schema.json": DocumentParseIdentitySchemaV08,
    "source-bundle-member-provenance.schema.json": SourceBundleMemberProvenanceSchemaV08,
    "source-bundle-revision.schema.json": SourceBundleRevisionSchemaV08,
    "source-egress-policy-snapshot.schema.json": SourceEgressPolicySnapshotSchemaV08,
    "dataset-manifest.schema.json": DatasetManifestSchemaV08,
}


def render_phase1_schemas() -> dict[str, bytes]:
    return {
        name: (
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        for name, model in PHASE1_SCHEMAS.items()
    }


def write_phase1_schemas(repository_root: Path) -> dict[str, Path]:
    target_directory = repository_root.resolve() / "contracts" / "schemas" / "v0.1.0"
    target_directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, content in render_phase1_schemas().items():
        target = target_directory / name
        target.write_bytes(content)
        written[name] = target
    return written


def render_phase2_schemas() -> dict[str, bytes]:
    return {
        name: (
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        for name, model in PHASE2_SCHEMAS.items()
    }


def write_phase2_schemas(repository_root: Path) -> dict[str, Path]:
    target_directory = repository_root.resolve() / "contracts" / "schemas" / "v0.2.0"
    target_directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, content in render_phase2_schemas().items():
        target = target_directory / name
        target.write_bytes(content)
        written[name] = target
    return written


def render_phase3_schemas() -> dict[str, bytes]:
    return {
        name: (
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        for name, model in PHASE3_SCHEMAS.items()
    }


def write_phase3_schemas(repository_root: Path) -> dict[str, Path]:
    target_directory = repository_root.resolve() / "contracts" / "schemas" / "v0.3.0"
    target_directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, content in render_phase3_schemas().items():
        target = target_directory / name
        target.write_bytes(content)
        written[name] = target
    return written


def render_phase4_schemas() -> dict[str, bytes]:
    return {
        name: (
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        for name, model in PHASE4_SCHEMAS.items()
    }


def write_phase4_schemas(repository_root: Path) -> dict[str, Path]:
    target_directory = repository_root.resolve() / "contracts" / "schemas" / "v0.4.0"
    target_directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, content in render_phase4_schemas().items():
        target = target_directory / name
        target.write_bytes(content)
        written[name] = target
    return written


def render_phase6_schemas() -> dict[str, bytes]:
    return {
        name: (
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        for name, model in PHASE6_SCHEMAS.items()
    }


def write_phase6_schemas(repository_root: Path) -> dict[str, Path]:
    target_directory = repository_root.resolve() / "contracts" / "schemas" / "v0.5.0"
    target_directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, content in render_phase6_schemas().items():
        target = target_directory / name
        target.write_bytes(content)
        written[name] = target
    return written


def render_phase7_schemas() -> dict[str, bytes]:
    return {
        name: (
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        for name, model in PHASE7_SCHEMAS.items()
    }


def write_phase7_schemas(repository_root: Path) -> dict[str, Path]:
    target_directory = repository_root.resolve() / "contracts" / "schemas" / "v0.6.0"
    target_directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, content in render_phase7_schemas().items():
        target = target_directory / name
        target.write_bytes(content)
        written[name] = target
    return written


def render_phase8_schemas() -> dict[str, bytes]:
    return {
        name: (
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        for name, model in PHASE8_SCHEMAS.items()
    }


def write_phase8_schemas(repository_root: Path) -> dict[str, Path]:
    target_directory = repository_root.resolve() / "contracts" / "schemas" / "v0.7.0"
    target_directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, content in render_phase8_schemas().items():
        target = target_directory / name
        target.write_bytes(content)
        written[name] = target
    return written


def render_phase9b_schemas() -> dict[str, bytes]:
    return {
        name: (
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True)
            + "\n"
        ).encode("utf-8")
        for name, model in PHASE9B_SCHEMAS.items()
    }


def write_phase9b_schemas(repository_root: Path) -> dict[str, Path]:
    target_directory = repository_root.resolve() / "contracts" / "schemas" / "v0.8.0"
    target_directory.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, content in render_phase9b_schemas().items():
        target = target_directory / name
        target.write_bytes(content)
        written[name] = target
    return written


def render_evidence_anchor_schemas() -> dict[str, bytes]:
    return {
        "reader-anchor.schema.json": (
            json.dumps(
                ReaderAnchor.model_json_schema(), ensure_ascii=False, indent=2, sort_keys=True
            )
            + "\n"
        ).encode("utf-8")
    }


def write_evidence_anchor_schemas(repository_root: Path) -> dict[str, Path]:
    target = repository_root.resolve() / "contracts" / "schemas" / "v0.9.0"
    target.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, content in render_evidence_anchor_schemas().items():
        paths[name] = target / name
        paths[name].write_bytes(content)
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Export versioned DeepAha JSON Schemas")
    parser.add_argument("repository_root", type=Path)
    parser.add_argument(
        "--version",
        choices=(
            "0.1.0",
            "0.2.0",
            "0.3.0",
            "0.4.0",
            "0.5.0",
            "0.6.0",
            "0.7.0",
            "0.8.0",
            "0.9.0",
        ),
        default="0.1.0",
    )
    arguments = parser.parse_args()
    if arguments.version == "0.9.0":
        write_evidence_anchor_schemas(arguments.repository_root)
    elif arguments.version == "0.8.0":
        write_phase9b_schemas(arguments.repository_root)
    elif arguments.version == "0.7.0":
        write_phase8_schemas(arguments.repository_root)
    elif arguments.version == "0.6.0":
        write_phase7_schemas(arguments.repository_root)
    elif arguments.version == "0.5.0":
        write_phase6_schemas(arguments.repository_root)
    elif arguments.version == "0.4.0":
        write_phase4_schemas(arguments.repository_root)
    elif arguments.version == "0.3.0":
        write_phase3_schemas(arguments.repository_root)
    elif arguments.version == "0.2.0":
        write_phase2_schemas(arguments.repository_root)
    else:
        write_phase1_schemas(arguments.repository_root)


if __name__ == "__main__":
    main()

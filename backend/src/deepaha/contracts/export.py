import argparse
import json
from pathlib import Path

from pydantic import BaseModel

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Export versioned DeepAha JSON Schemas")
    parser.add_argument("repository_root", type=Path)
    parser.add_argument(
        "--version",
        choices=("0.1.0", "0.2.0", "0.3.0", "0.4.0"),
        default="0.1.0",
    )
    arguments = parser.parse_args()
    if arguments.version == "0.4.0":
        write_phase4_schemas(arguments.repository_root)
    elif arguments.version == "0.3.0":
        write_phase3_schemas(arguments.repository_root)
    elif arguments.version == "0.2.0":
        write_phase2_schemas(arguments.repository_root)
    else:
        write_phase1_schemas(arguments.repository_root)


if __name__ == "__main__":
    main()

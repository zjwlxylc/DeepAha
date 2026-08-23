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


def main() -> None:
    parser = argparse.ArgumentParser(description="Export versioned DeepAha JSON Schemas")
    parser.add_argument("repository_root", type=Path)
    parser.add_argument("--version", choices=("0.1.0", "0.2.0"), default="0.1.0")
    arguments = parser.parse_args()
    if arguments.version == "0.2.0":
        write_phase2_schemas(arguments.repository_root)
    else:
        write_phase1_schemas(arguments.repository_root)


if __name__ == "__main__":
    main()

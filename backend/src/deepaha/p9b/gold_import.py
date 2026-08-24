import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from deepaha.contracts.phase9b import (
    GoldAdjudicationDecisionSchemaV08,
    GoldAnnotationSubmissionSchemaV08,
    GoldAnnotationTaskSchemaV08,
    GoldTruthVersionSchemaV08,
)
from deepaha.core.settings import Settings
from deepaha.p9b.annotation import GoldWorkflow
from deepaha.p9b.gold import GoldRepository


class GoldImportError(ValueError):
    pass


@dataclass(frozen=True)
class GoldImportBundle:
    task: GoldAnnotationTaskSchemaV08
    submissions: tuple[
        GoldAnnotationSubmissionSchemaV08,
        GoldAnnotationSubmissionSchemaV08,
    ]
    adjudication: GoldAdjudicationDecisionSchemaV08 | None
    truth: GoldTruthVersionSchemaV08


def validate_gold_import(
    payload: dict[str, object], *, allow_synthetic: bool = False
) -> GoldImportBundle:
    expected_keys = {"task", "submissions", "adjudication", "truth"}
    if set(payload) != expected_keys:
        raise GoldImportError("Gold import envelope has unexpected or missing keys")
    task = GoldAnnotationTaskSchemaV08.model_validate(payload["task"])
    if not allow_synthetic and any(
        reference.startswith(("synthetic:", "synthetic-fixture:"))
        for reference in task.role_attestation_references.values()
    ):
        raise GoldImportError("synthetic identity attestations cannot be imported as real Gold")
    raw_submissions = payload["submissions"]
    if not isinstance(raw_submissions, list) or len(raw_submissions) != 2:
        raise GoldImportError("Gold import requires exactly two independent submissions")
    submissions = (
        GoldAnnotationSubmissionSchemaV08.model_validate(raw_submissions[0]),
        GoldAnnotationSubmissionSchemaV08.model_validate(raw_submissions[1]),
    )
    annotation, verification = submissions
    workflow = GoldWorkflow(task)
    workflow.accept_submission(annotation)
    workflow.accept_submission(verification)
    raw_adjudication = payload["adjudication"]
    adjudication = (
        GoldAdjudicationDecisionSchemaV08.model_validate(raw_adjudication)
        if raw_adjudication is not None
        else None
    )
    if adjudication is not None:
        workflow.accept_adjudication(adjudication)
    truth = GoldTruthVersionSchemaV08.model_validate(payload["truth"])
    expected_truth = workflow.freeze_truth(
        curator_identity=truth.curator_identity,
        gold_truth_version_id=truth.gold_truth_version_id,
        version=truth.version,
        frozen_at=truth.frozen_at,
        supersedes_truth_version_id=truth.supersedes_truth_version_id,
        revision_reason_code=truth.revision_reason_code,
    )
    if expected_truth != truth:
        raise GoldImportError("Gold truth is not the canonical result of its governed reviews")
    return GoldImportBundle(task, submissions, adjudication, truth)


def persist_gold_import(session: Session, bundle: GoldImportBundle) -> None:
    repository = GoldRepository(session)
    repository.persist_task(bundle.task)
    for submission in bundle.submissions:
        repository.persist_submission(submission)
    if bundle.adjudication is not None:
        repository.persist_adjudication(bundle.adjudication)
    repository.persist_truth(bundle.truth)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate or import governed P9-B Gold JSON")
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--persist",
        action="store_true",
        help="Persist after validation; the default is a read-only dry run.",
    )
    arguments = parser.parse_args()
    payload = json.loads(arguments.input.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise GoldImportError("Gold import root must be an object")
    bundle = validate_gold_import(payload)
    if not arguments.persist:
        print(f"VALID Gold truth hash={bundle.truth.truth_hash} persist=NO")
        return
    database_url = Settings().database_url
    if database_url is None:
        raise GoldImportError("DEEPAHA_DATABASE_URL is required for --persist")
    engine = create_engine(database_url)
    try:
        with Session(engine) as session, session.begin():
            persist_gold_import(session, bundle)
    finally:
        engine.dispose()
    print(f"IMPORTED Gold truth hash={bundle.truth.truth_hash}")


if __name__ == "__main__":
    main()


__all__ = [
    "GoldImportBundle",
    "GoldImportError",
    "persist_gold_import",
    "validate_gold_import",
]

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from typing import Literal
from uuid import UUID

from sqlalchemy.orm import Session

from deepaha.contracts.phase4 import (
    EligibilityStatus,
    EvaluationCaseResultSchemaV04,
    EvaluationComponent,
    EvaluationComponentVersionsSchemaV04,
    EvaluationMetricsSchemaV04,
    EvaluationRunSchemaV04,
    EvaluationRunStatus,
)
from deepaha.eligibility.engine import ENGINE_VERSION
from deepaha.evaluation.fixtures import FixtureBundle, GoldenCaseFixture
from deepaha.evaluation.models import EvaluationCaseResultModel, EvaluationRunModel
from deepaha.rules.compiler import COMPILER_VERSION

EVIDENCE_LABEL: Literal["SYNTHETIC_EVALUATION_ONLY"] = "SYNTHETIC_EVALUATION_ONLY"


class UnexpectedIneligibleError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CaseEvaluation:
    actual_status: EligibilityStatus
    match_snapshot_id: UUID
    input_sha256: str
    reason_codes: tuple[str, ...]
    replay_matched: bool


@dataclass(frozen=True, slots=True)
class EvaluationCaseReport:
    case_id: str
    expected_status: EligibilityStatus
    actual_status: EligibilityStatus
    passed: bool
    unexpected_ineligible: bool
    match_snapshot_id: UUID
    input_sha256: str
    reason_codes: tuple[str, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "case_id": self.case_id,
            "expected_status": self.expected_status.value,
            "actual_status": self.actual_status.value,
            "passed": self.passed,
            "unexpected_ineligible": self.unexpected_ineligible,
            "match_snapshot_id": str(self.match_snapshot_id),
            "input_sha256": self.input_sha256,
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True, slots=True)
class EvaluationMetrics:
    case_count: int
    passed_case_count: int
    expected_ineligible_count: int
    actual_ineligible_count: int
    unexpected_ineligible_count: int
    unexpected_ineligible_case_ids: tuple[str, ...]
    replay_mismatch_count: int
    status_counts: dict[EligibilityStatus, int]

    def to_contract(self) -> EvaluationMetricsSchemaV04:
        return EvaluationMetricsSchemaV04(
            total_cases=self.case_count,
            passed_cases=self.passed_case_count,
            expected_ineligible_count=self.expected_ineligible_count,
            actual_ineligible_count=self.actual_ineligible_count,
            unexpected_ineligible_count=self.unexpected_ineligible_count,
            unexpected_ineligible_case_ids=self.unexpected_ineligible_case_ids,
            replay_mismatch_count=self.replay_mismatch_count,
            status_counts=self.status_counts,
        )

    def to_payload(self) -> dict[str, object]:
        return self.to_contract().model_dump(mode="json")


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    dataset_id: str
    dataset_version: str
    dataset_sha256: str
    scenario_clock: datetime
    evidence_label: Literal["SYNTHETIC_EVALUATION_ONLY"]
    component_versions: EvaluationComponentVersionsSchemaV04
    case_results: tuple[EvaluationCaseReport, ...]
    metrics: EvaluationMetrics
    report_sha256: str

    def to_payload(self) -> dict[str, object]:
        return self._digest_payload() | {"report_sha256": self.report_sha256}

    def _digest_payload(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_version": self.dataset_version,
            "dataset_sha256": self.dataset_sha256,
            "scenario_clock": self.scenario_clock.isoformat(),
            "evidence_label": self.evidence_label,
            "component_versions": self.component_versions.model_dump(mode="json"),
            "case_results": [result.to_payload() for result in self.case_results],
            "metrics": self.metrics.to_payload(),
        }


CaseEvaluator = Callable[[GoldenCaseFixture], CaseEvaluation]


def run_synthetic_evaluation(
    bundle: FixtureBundle,
    evaluator: CaseEvaluator,
) -> EvaluationReport:
    case_results: list[EvaluationCaseReport] = []
    for case in sorted(bundle.golden_cases, key=lambda item: item.case_id):
        evaluation = evaluator(case)
        unexpected = (
            evaluation.actual_status is EligibilityStatus.INELIGIBLE
            and case.expected_status is not EligibilityStatus.INELIGIBLE
        )
        if unexpected and case.protected_from_unexpected_ineligible:
            raise UnexpectedIneligibleError(
                f"protected Golden case unexpectedly INELIGIBLE: {case.case_id}"
            )
        reason_codes = set(evaluation.reason_codes)
        if not evaluation.replay_matched:
            reason_codes.add("REPLAY_MISMATCH")
        case_results.append(
            EvaluationCaseReport(
                case_id=case.case_id,
                expected_status=case.expected_status,
                actual_status=evaluation.actual_status,
                passed=evaluation.actual_status is case.expected_status,
                unexpected_ineligible=unexpected,
                match_snapshot_id=evaluation.match_snapshot_id,
                input_sha256=evaluation.input_sha256,
                reason_codes=tuple(sorted(reason_codes)),
            )
        )
    metrics = _metrics(tuple(case_results))
    component_versions = EvaluationComponentVersionsSchemaV04(
        contract="0.4.0",
        compiler=COMPILER_VERSION,
        engine=ENGINE_VERSION,
        major_catalog=bundle.major_catalog.version,
        major_mapping=bundle.major_mapping.version,
    )
    report_without_digest = EvaluationReport(
        dataset_id=bundle.dataset_id,
        dataset_version=bundle.dataset_version,
        dataset_sha256=bundle.manifest_sha256,
        scenario_clock=bundle.scenario_clock,
        evidence_label=EVIDENCE_LABEL,
        component_versions=component_versions,
        case_results=tuple(case_results),
        metrics=metrics,
        report_sha256="",
    )
    digest = sha256(_canonical_bytes(report_without_digest._digest_payload())).hexdigest()
    return EvaluationReport(
        dataset_id=report_without_digest.dataset_id,
        dataset_version=report_without_digest.dataset_version,
        dataset_sha256=report_without_digest.dataset_sha256,
        scenario_clock=report_without_digest.scenario_clock,
        evidence_label=report_without_digest.evidence_label,
        component_versions=report_without_digest.component_versions,
        case_results=report_without_digest.case_results,
        metrics=report_without_digest.metrics,
        report_sha256=digest,
    )


def persist_evaluation_run(
    session: Session,
    report: EvaluationReport,
    *,
    run_id: UUID,
    started_at: datetime,
    completed_at: datetime,
) -> EvaluationRunSchemaV04:
    case_contracts = tuple(
        EvaluationCaseResultSchemaV04(
            case_id=result.case_id,
            expected_status=result.expected_status,
            actual_status=result.actual_status,
            passed=result.passed,
            match_snapshot_id=result.match_snapshot_id,
            input_sha256=result.input_sha256,
            unexpected_ineligible=result.unexpected_ineligible,
            reason_codes=result.reason_codes,
        )
        for result in report.case_results
    )
    contract = EvaluationRunSchemaV04(
        run_id=run_id,
        dataset_id=report.dataset_id,
        dataset_version=report.dataset_version,
        dataset_sha256=report.dataset_sha256,
        evidence_label=report.evidence_label,
        scenario_clock=report.scenario_clock,
        report_sha256=report.report_sha256,
        component=EvaluationComponent.ELIGIBILITY,
        component_versions=report.component_versions,
        synthetic=True,
        status=EvaluationRunStatus.COMPLETED,
        case_results=case_contracts,
        metrics=report.metrics.to_contract(),
        started_at=started_at,
        completed_at=completed_at,
        error_summary=None,
    )
    session.add(
        EvaluationRunModel(
            run_id=contract.run_id,
            dataset_id=contract.dataset_id,
            dataset_version=contract.dataset_version,
            dataset_sha256=contract.dataset_sha256,
            evidence_label=contract.evidence_label,
            scenario_clock=contract.scenario_clock,
            report_sha256=contract.report_sha256,
            component=contract.component.value,
            component_versions=contract.component_versions.model_dump(mode="json"),
            synthetic=contract.synthetic,
            status=contract.status.value,
            metrics=contract.metrics.model_dump(mode="json") if contract.metrics else None,
            started_at=contract.started_at,
            completed_at=contract.completed_at,
            error_summary=contract.error_summary,
        )
    )
    session.flush()
    session.add_all(
        [
            EvaluationCaseResultModel(
                run_id=contract.run_id,
                case_id=result.case_id,
                expected_status=result.expected_status.value,
                actual_status=result.actual_status.value,
                passed=result.passed,
                match_snapshot_id=result.match_snapshot_id,
                input_sha256=result.input_sha256,
                unexpected_ineligible=result.unexpected_ineligible,
                reason_codes=list(result.reason_codes),
            )
            for result in contract.case_results
        ]
    )
    session.flush()
    return contract


def _metrics(results: tuple[EvaluationCaseReport, ...]) -> EvaluationMetrics:
    status_counts = {status: 0 for status in EligibilityStatus}
    for result in results:
        status_counts[result.actual_status] += 1
    unexpected_case_ids = tuple(
        result.case_id for result in results if result.unexpected_ineligible
    )
    return EvaluationMetrics(
        case_count=len(results),
        passed_case_count=sum(result.passed for result in results),
        expected_ineligible_count=sum(
            result.expected_status is EligibilityStatus.INELIGIBLE for result in results
        ),
        actual_ineligible_count=status_counts[EligibilityStatus.INELIGIBLE],
        unexpected_ineligible_count=len(unexpected_case_ids),
        unexpected_ineligible_case_ids=unexpected_case_ids,
        replay_mismatch_count=sum(
            "REPLAY_MISMATCH" in result.reason_codes for result in results
        ),
        status_counts=status_counts,
    )


def _canonical_bytes(payload: object) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


__all__ = [
    "CaseEvaluation",
    "CaseEvaluator",
    "EvaluationCaseReport",
    "EvaluationMetrics",
    "EvaluationReport",
    "UnexpectedIneligibleError",
    "persist_evaluation_run",
    "run_synthetic_evaluation",
]

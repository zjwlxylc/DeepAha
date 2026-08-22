from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
PRIOR_PORTS = (
    "55432",
    "55000",
    "55433",
    "55001",
    "55434",
    "55002",
    "55435",
    "55003",
    "55436",
    "55004",
)
PRIOR_PROJECTS = tuple(f"deepaha-phase{phase}-" for phase in range(2, 7))


def _phase7_verifier() -> str:
    return (REPOSITORY_ROOT / "scripts" / "verify-phase7.ps1").read_text("utf-8")


def test_phase7_verifier_uses_only_exact_isolated_project_and_ports() -> None:
    verifier = _phase7_verifier()
    compose = (REPOSITORY_ROOT / "infra" / "compose.phase7.yaml").read_text("utf-8")
    normalized = verifier.replace("\\", "/").lower()

    assert "55437" in compose and "55005" in compose
    for required in (
        "compose_project_name",
        "deepaha-phase7-",
        "infra/compose.phase7.yaml",
        "assert-portavailableorowned 55437",
        "assert-portavailableorowned 55005",
        "finally",
        "down --volumes --remove-orphans",
    ):
        assert required in normalized
    for forbidden in (
        *PRIOR_PORTS,
        *PRIOR_PROJECTS,
        "docker system prune",
        "live_source",
        "record_human_run",
        "humanvalidationrunwrite",
        "openai",
        "anthropic",
    ):
        assert forbidden not in normalized


def test_phase7_verifier_covers_contracts_services_integrations_and_boundaries() -> None:
    normalized = _phase7_verifier().replace("\\", "/").lower()

    for required in (
        "scripts/verify.ps1",
        "tests/contracts/test_phase1_contracts.py",
        "tests/contracts/test_phase2_contracts.py",
        "tests/contracts/test_phase3_contracts.py",
        "tests/contracts/test_phase4_contracts.py",
        "tests/contracts/test_phase6_contracts.py",
        "tests/contracts/test_phase7_contracts.py",
        "tests/feedback",
        "tests/review",
        "tests/validation",
        "tests/api/test_feedback.py",
        "tests/api/test_review.py",
        "tests/test_phase7_verifier_scope.py",
        "tests/integration/test_phase7_feedback_submission.py",
        "tests/integration/test_phase7_feedback_isolation.py",
        "tests/integration/test_phase7_reviewer_authorization.py",
        "tests/integration/test_phase7_persistence.py",
        "tests/integration/test_phase7_review_workflow.py",
        "tests/integration/test_phase7_validation_gate.py",
        "tests/integration/test_phase7_vertical_slice.py",
        "tests/integration/test_phase7_transaction_rollback.py",
        "alembic upgrade head",
        "alembic downgrade 20260822_0006",
        "alembic check",
        "pnpm lint",
        "pnpm typecheck",
        "pnpm test",
        "pnpm build",
        "synthetic_feedback_workflow_only",
        "real participants=0",
        "human track=not_started",
        "release qualification=not_started",
        "release decision=hold_missing_human_evidence",
    ):
        assert required in normalized


def test_ci_keeps_inherited_jobs_and_adds_scoped_phase7_job() -> None:
    ci = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")

    for inherited in (
        "backend-quality:",
        "web-quality:",
        "integration:",
        "phase3-resolution:",
        "phase4-eligibility:",
        "phase5-public-trust:",
        "phase6-profile-action:",
    ):
        assert f"  {inherited}" in ci
    assert "codex/phase-7-feedback-review-validation" in ci
    job = ci[ci.index("  phase7-feedback-review:") :]
    for required in (
        '"55437:5432"',
        '"55005:5000"',
        "test_phase7_verifier_scope.py",
        "test_phase7_persistence.py",
        "test_phase7_review_workflow.py",
        "test_phase7_validation_gate.py",
        "test_phase7_vertical_slice.py",
        "test_phase7_transaction_rollback.py",
        "alembic downgrade 20260822_0006",
        "pnpm lint",
        "pnpm typecheck",
        "pnpm test",
        "pnpm build",
    ):
        assert required in job
    for forbidden in (*PRIOR_PORTS, *PRIOR_PROJECTS, "live_source"):
        assert forbidden not in job.lower()

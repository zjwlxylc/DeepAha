from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
PRIOR_PORTS = ("55432", "55000", "55433", "55001", "55434", "55002", "55435", "55003")


def test_phase6_verifier_uses_only_its_isolated_project_and_ports() -> None:
    verifier = (REPOSITORY_ROOT / "scripts" / "verify-phase6.ps1").read_text("utf-8")
    compose = (REPOSITORY_ROOT / "infra" / "compose.phase6.yaml").read_text("utf-8")
    normalized = verifier.replace("\\", "/").lower()

    assert "55436" in compose and "55004" in compose
    for required in (
        "compose_project_name",
        "deepaha-phase6-",
        "infra/compose.phase6.yaml",
        "assert-portavailableorowned 55436",
        "assert-portavailableorowned 55004",
        "finally",
        "down --volumes --remove-orphans",
    ):
        assert required in normalized
    for forbidden in (
        *PRIOR_PORTS,
        "deepaha-phase2-",
        "deepaha-phase3-",
        "deepaha-phase4-",
        "deepaha-phase5-",
        "docker system prune",
        "live_source",
    ):
        assert forbidden not in normalized


def test_phase6_verifier_covers_backend_web_migrations_and_evidence_boundary() -> None:
    verifier = (REPOSITORY_ROOT / "scripts" / "verify-phase6.ps1").read_text("utf-8")
    normalized = verifier.replace("\\", "/").lower()

    for required in (
        "scripts/verify.ps1",
        "tests/contracts/test_phase6_contracts.py",
        "tests/personal",
        "tests/api/test_personal.py",
        "tests/test_phase6_verifier_scope.py",
        "tests/integration/test_phase6_profile_persistence.py",
        "tests/integration/test_phase6_personal_match_replay.py",
        "tests/integration/test_phase6_personal_api.py",
        "tests/integration/test_phase6_vertical_slice.py",
        "tests/integration/test_phase6_user_isolation.py",
        "alembic upgrade head",
        "alembic downgrade 20260822_0005",
        "alembic check",
        "pnpm lint",
        "pnpm typecheck",
        "pnpm test",
        "pnpm build",
        "synthetic_fixture_only",
        "real users=0",
        "release qualification: not_started",
        "phase 6 v0.5 contract maturity: implemented",
    ):
        assert required in normalized


def test_ci_keeps_inherited_jobs_and_adds_scoped_phase6_job() -> None:
    ci = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")

    for inherited in (
        "backend-quality:",
        "web-quality:",
        "integration:",
        "phase3-resolution:",
        "phase4-eligibility:",
        "phase5-public-trust:",
    ):
        assert f"  {inherited}" in ci
    assert "codex/phase-6-profile-match-personal-action" in ci
    job = ci[ci.index("  phase6-profile-action:") :]
    for required in (
        '"55436:5432"',
        '"55004:5000"',
        "test_phase6_verifier_scope.py",
        "test_phase6_vertical_slice.py",
        "test_phase6_user_isolation.py",
        "alembic downgrade 20260822_0005",
        "pnpm test",
        "pnpm build",
    ):
        assert required in job
    for forbidden in (*PRIOR_PORTS, "live_source"):
        assert forbidden not in job.lower()

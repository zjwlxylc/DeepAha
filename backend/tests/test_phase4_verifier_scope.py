from pathlib import Path

REPOSITORY_ROOT = Path(__file__).parents[2]
GATE_FILENAMES = {
    "README.md",
    "acceptance-results.md",
    "code-review.md",
    "deferred-decisions.md",
    "evaluation-summary.md",
    "operations.md",
    "security-and-compliance.md",
    "test-summary.md",
}


def test_phase4_verifier_uses_only_its_isolated_project_and_ports() -> None:
    verifier = (REPOSITORY_ROOT / "scripts" / "verify-phase4.ps1").read_text("utf-8")
    compose = (REPOSITORY_ROOT / "infra" / "compose.phase4.yaml").read_text("utf-8")

    assert "55434" in compose and "55002" in compose
    assert "COMPOSE_PROJECT_NAME" in verifier
    assert "deepaha-phase4-" in verifier
    assert "infra/compose.phase4.yaml" in verifier.replace("\\", "/")
    for forbidden in (
        "55432",
        "55000",
        "55433",
        "55001",
        "deepaha-phase2-live-gate",
        "verify-phase1",
        "verify-phase2",
        "verify-phase3",
        "live_source",
        "playwright",
        "docling",
        "model gateway",
        "provider",
        "observation",
    ):
        assert forbidden not in verifier.lower()


def test_phase4_verifier_covers_offline_quality_and_integration_checks() -> None:
    verifier = (REPOSITORY_ROOT / "scripts" / "verify-phase4.ps1").read_text("utf-8")
    normalized = verifier.replace("\\", "/").lower()

    for required in (
        "docker",
        "uv",
        "ruff format --check",
        "ruff check",
        "mypy",
        "test_phase4_contracts.py",
        "tests/rules",
        "tests/eligibility",
        "tests/evaluation",
        "test_phase4_persistence_contract.py",
        "test_phase4_match_replay.py",
        "test_phase4_evaluation_run.py",
        "implementation: implemented",
        "engineering verification: pass",
        "release qualification: not_started",
        "v0.4 contract maturity: implemented",
        "synthetic_evaluation_only",
    ):
        assert required in normalized


def test_ci_has_a_phase4_scoped_job_and_fixed_service_ports() -> None:
    ci = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text("utf-8")

    assert "codex/phase-4-rules-eligibility-evaluation" in ci
    assert "phase4-eligibility:" in ci
    assert '"55434:5432"' in ci
    assert '"55002:5000"' in ci
    assert "test_phase4_evaluation_run.py" in ci
    assert "live_source" not in _phase4_job(ci)


def test_gate_package_separates_engineering_and_release_states() -> None:
    gate_directory = REPOSITORY_ROOT / "docs" / "gates" / "phase-4"
    assert {path.name for path in gate_directory.glob("*.md")} == GATE_FILENAMES
    for filename in GATE_FILENAMES:
        text = (gate_directory / filename).read_text("utf-8")
        assert "implemented" in text.lower()
        assert "locally verified" in text.lower()
        assert "remote CI" in text
        assert "synthetic evaluation" in text.lower()
        assert "Release Qualification" in text
        assert "Contract Maturity" in text
        assert "IMPLEMENTED_PENDING_PHASE2_PHASE3_GATES" not in text
        assert "BLOCKED_BY_PHASE2" not in text
    readme = (gate_directory / "README.md").read_text("utf-8")
    assert "Implementation: `IMPLEMENTED`" in readme
    assert "Engineering Gate: `CLOSED`" in readme
    assert "Release Qualification: `NOT_STARTED`" in readme
    assert "Contract Maturity: `IMPLEMENTED`" in readme


def test_operations_never_touches_upstream_live_observation() -> None:
    operations = (REPOSITORY_ROOT / "docs" / "gates" / "phase-4" / "operations.md").read_text(
        "utf-8"
    )
    lowered = operations.lower()
    for forbidden in (
        "deepaha-phase2-live-gate",
        "55432",
        "55000",
        "stop-phase2",
        "down phase2",
    ):
        assert forbidden not in lowered


def _phase4_job(ci: str) -> str:
    start = ci.index("  phase4-eligibility:")
    return ci[start:]

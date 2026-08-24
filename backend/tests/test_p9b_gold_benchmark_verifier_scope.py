from pathlib import Path

ROOT = Path(__file__).parents[2]


def test_gold_verifier_runs_required_regressions_and_preserves_evidence_boundary() -> None:
    script = (ROOT / "scripts/verify-p9b-gold-benchmark.ps1").read_text(encoding="utf-8")

    assert "scripts/verify.ps1" in script
    assert "tests/contracts/test_phase9b_contracts.py" in script
    assert "tests/integration/test_p9b_gold_migration.py" in script
    assert "uv run pytest -m integration --strict-markers" in script
    assert "uv run alembic downgrade 20260824_0013" in script
    assert "Real Gold entries=0 / NOT_OBSERVED" in script
    assert "Locked Acceptance benchmark=NOT_RUN" in script
    assert "Release Qualification=NOT_STARTED" in script

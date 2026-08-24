from pathlib import Path


def test_fact_chain_verifier_covers_gate_and_regression_boundaries() -> None:
    root = Path(__file__).parents[2]
    verifier = root / "scripts" / "verify-p9b-fact-chain.ps1"
    normalized = verifier.read_text("utf-8").replace("\\", "/").lower()

    for required in (
        "^deepaha-p9b-facts-[a-z0-9][a-z0-9-]*$",
        "scripts/verify.ps1",
        "tests/contracts/test_phase9b_contracts.py",
        "tests/p9b/test_fact_lifecycle.py",
        "tests/p9b/test_rule_promotion.py",
        "tests/integration/test_p9b_fact_persistence.py",
        "tests/integration/test_p9b_fact_lifecycle_migration.py",
        "pytest -m integration --strict-markers",
        "alembic downgrade 20260824_0012",
        "alembic upgrade head",
        "alembic check",
        "git diff --check",
        "down --volumes --remove-orphans",
    ):
        assert required in normalized


def test_fact_chain_verifier_does_not_start_release_qualification_or_unit_activation() -> None:
    root = Path(__file__).parents[2]
    normalized = (root / "scripts" / "verify-p9b-fact-chain.ps1").read_text("utf-8").lower()

    assert "run-source-acquisition-qualification.ps1" not in normalized
    assert "activation=active" not in normalized
    assert "release qualification=not_started" in normalized

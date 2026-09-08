"""Replay retained synthetic outputs without DB, network or admission of cached JSON.

Run with the backend virtualenv and PYTHONPATH=backend/src, passing the retained
JSON files. Code hashes normalize CRLF to LF for cross-platform checkout replay.
This verifies deterministic calculation only, never current DB state or approval.
"""

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from deepaha.contracts.phase4 import ProfileSnapshotSchemaV04
from deepaha.rules.major import load_approved_major_mapping, load_major_catalog
from deepaha.unit_qualification.contracts import UnitQualificationPlan
from deepaha.unit_qualification.evaluator import UnitEvaluationInput, evaluate_unit_qualification

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("evidence_files", type=Path, nargs="+")
args = parser.parse_args()
backend = Path(__file__).resolve().parents[3] / "backend"
summaries = []
for path in args.evidence_files:
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["mode"] == "SYNTHETIC_DATABASE_TO_ENGINE_REPLAY_ONLY"
    assert document["code_hash_normalization"] == "CRLF_TO_LF"
    for relative, expected_hash in document["input_files"].items():
        source = (backend / relative).resolve(strict=True)
        assert source.is_relative_to(backend), "source outside backend"
        actual_hash = sha256(source.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        assert actual_hash == expected_hash, relative
    plan = UnitQualificationPlan.model_validate(document["trusted_snapshot"]["plan"])
    # Use the existing strict asset loaders for embedded synthetic catalogs.
    with TemporaryDirectory(prefix="deepaha-synthetic-unit-replay-") as directory:
        assets = Path(directory)
        for name in ("major_catalog", "major_mapping"):
            (assets / name).write_text(json.dumps(document[name]), encoding="utf-8")
        catalog = load_major_catalog(assets / "major_catalog")
        mapping = load_approved_major_mapping(assets / "major_mapping", catalog)
    cases = []
    assert document["cases"], "empty replay cannot pass"
    for case in document["cases"]:
        profile = ProfileSnapshotSchemaV04.model_validate(case["profile"])
        assert profile.synthetic, "not a synthetic profile"
        result = evaluate_unit_qualification(
            UnitEvaluationInput(
                plan=plan,
                expected_target=plan.target,
                profile_snapshot_id=profile.profile_snapshot_id,
                profile_version=profile.version,
                profile_schema_version=profile.profile_schema_version,
                profile_attributes=profile.attributes.model_dump(mode="json"),
                major_catalog=catalog,
                major_mapping=mapping,
                scenario_clock=profile.scenario_clock,
                evidence_as_of=datetime.fromisoformat(case["result"]["evidence_as_of"]),
            )
        )
        assert json.loads(json.dumps(asdict(result), default=str)) == case["result"]
        assert result.status == "UNCERTAIN"
        cases.append({"engine_status": result.engine_status, "status": result.status})
    summaries.append({"evidence": path.name, "deterministic_replay": "PASS", "cases": cases})
print(json.dumps({"database_writes": 0, "network_calls": 0, "replays": summaries}, indent=2))

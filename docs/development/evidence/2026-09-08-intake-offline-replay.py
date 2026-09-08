"""Replay the frozen calibration through this checkout, without network or database."""

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from deepaha.investigations import delivery

parser = argparse.ArgumentParser()
parser.add_argument("--case-directory", type=Path, required=True)
parser.add_argument("--baseline", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
case = args.case_directory.resolve(strict=True)
baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
results = {name: (case / "result" / name).read_bytes() for name in delivery._FILES}
manifest = delivery.preflight_manifest(results)
originals = {}
paths = [case / "result" / name for name in results]
for identity, relative in manifest:
    path = (case / relative).resolve(strict=True)
    if not path.is_relative_to(case):
        raise ValueError("artifact outside case directory")
    paths.append(path)
    originals[identity] = path.read_bytes()


def hashes() -> dict[str, str]:
    return {path.relative_to(case).as_posix(): sha256(path.read_bytes()).hexdigest() for path in paths}


before = hashes()
expected = {
    key.replace("\\", "/"): value
    for key, value in baseline["original_file_hashes_before"].items()
}
assert before == expected, "input differs from the frozen calibration"
validated = delivery.validate_delivery(results, originals)
artifact_types = {item.artifact_id: item.media_type for item in validated.artifacts}
rows = [
    {
        "entity_id": fact.entity_id,
        "field": fact.field,
        "artifact_id": ref.artifact_id,
        "quote": ref.quote,
        "locator": ref.locator,
        "verdict": "PASS" if ref.mechanically_verified else "UNVERIFIED",
    }
    for fact in validated.facts
    for ref in fact.evidence
]
counts = Counter(row["verdict"] for row in rows)
word = [row for row in rows if artifact_types[row["artifact_id"]] == "application/msword"]
headers = [
    row for row in rows
    if row["field"] == "education_degree_requirement" and row["quote"] == "学历、学位要求"
]
assert len(rows) == 124 and counts == {"PASS": 94, "UNVERIFIED": 30}
assert len(word) == 30 and all(row["verdict"] == "UNVERIFIED" for row in word)
assert len(headers) == 4 and all(row["verdict"] == "PASS" for row in headers)
assert before == hashes(), "original changed during replay"
report = {
    "checked_at": datetime.now(UTC).isoformat(),
    "case_id": baseline["case_id"],
    "verifier_path": str(Path(delivery.__file__).resolve()),
    "verifier_sha256": sha256(Path(delivery.__file__).read_bytes()).hexdigest(),
    "canonicalization_version": delivery.HTML_QUOTE_CANONICALIZATION_VERSION,
    "wma_calls": 0,
    "business_database_writes": 0,
    "schema": "PASS",
    "cross_file_consistency": "PASS",
    "original_hashes": before,
    "originals_unchanged": True,
    "counts": {"PASS": counts["PASS"], "FAIL": 0, "UNVERIFIED": counts["UNVERIFIED"]},
    "four_html_headers_pass": True,
    "delivery_verdict": "UNVERIFIED",
    "issues": list(validated.issues),
    "references": rows,
}
args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({key: report[key] for key in ("counts", "four_html_headers_pass", "delivery_verdict")}))

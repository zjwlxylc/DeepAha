"""Replay the frozen calibration through this checkout, without network or database."""

import argparse
import json
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from deepaha.investigations import delivery
from deepaha.evidence_verification.adapters.defaults import default_registry
from deepaha.evidence_verification.contracts import ArtifactInput
from deepaha.evidence_verification.verifier import EvidenceVerifier

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
validated = delivery.validate_legacy_delivery(results, originals)
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
verifier = EvidenceVerifier(default_registry())
by_id = {item.artifact_id: item for item in validated.artifacts}
comparisons = []
for row in rows:
    item = by_id[row['artifact_id']]
    result = verifier.verify(
        ArtifactInput(item.artifact_id, item.media_type, item.url, item.sha256, item.content),
        row['quote'], row['locator'],
    )
    comparisons.append({
        'entity_id': row['entity_id'], 'field': row['field'], 'legacy_verdict': row['verdict'],
        'new_result': asdict(result),
    })
new_counts = Counter(item['new_result']['verdict'] for item in comparisons)
regressions = [item for item in comparisons
               if item['legacy_verdict'] == 'PASS' and item['new_result']['verdict'] != 'PASS']
package = Path(delivery.__file__).parents[1] / 'evidence_verification'
report = {
    'checked_at': datetime.now(UTC).isoformat(), 'case_id': baseline['case_id'],
    'mode': 'SHADOW_ONLY', 'wma_calls': 0, 'business_database_writes': 0,
    'original_hashes_before': before, 'original_hashes_after': hashes(),
    'originals_unchanged': before == hashes(),
    'schema': 'PASS', 'cross_file_consistency': 'PASS',
    'production_counts': {'PASS': counts['PASS'], 'FAIL': 0, 'UNVERIFIED': counts['UNVERIFIED']},
    'shadow_counts': {key: new_counts[key] for key in ('PASS', 'FAIL', 'UNVERIFIED')},
    'legacy_pass_regressions': len(regressions),
    'delivery_verdict': 'UNVERIFIED',
    'reader_scope': 'HTML/PDF/XLSX registered; binary DOC remains unsupported',
    'source_hashes': {path.relative_to(package).as_posix(): sha256(path.read_bytes()).hexdigest()
                      for path in sorted(package.rglob('*.py'))},
    'shared_reader_hashes': {name: sha256((package.parent / name).read_bytes()).hexdigest()
                            for name in ('documents/html.py', 'documents/spreadsheet_reading.py',
                                         'investigations/delivery.py')},
    'four_html_headers_pass': all(item['new_result']['verdict'] == 'PASS'
                                  for item in comparisons if item['new_result']['quote'] == '学历、学位要求'),
    'inline_publication_scope_pass': all(item['new_result']['verdict'] == 'PASS'
                                         for item in comparisons if item['field'] == 'site_publish_time'),
    'references': comparisons,
}
args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({key: report[key] for key in ('production_counts', 'shadow_counts', 'legacy_pass_regressions', 'delivery_verdict')}))
for item in regressions:
    result = item['new_result']
    print(json.dumps({'entity_id': item['entity_id'], 'field': item['field'],
                      'quote': result['quote'], 'locator': result['original_locator'],
                      'reason_codes': result['reason_codes'], 'matches': len(result['matches'])}, ensure_ascii=False))
assert before == hashes(), 'original changed during shadow replay'
assert not regressions, 'shadow verifier regressed a legacy PASS'
assert new_counts == {'PASS': 94, 'UNVERIFIED': 30}

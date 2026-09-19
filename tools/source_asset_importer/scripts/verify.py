"""Run local tests and save auditable results; never configure a production target."""
from __future__ import annotations

import compileall
import importlib.metadata
import json
import os
import platform
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            stream.write(text)
        return len(text)

    def flush(self):
        for stream in self.streams:
            stream.flush()


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed_ids = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed_ids.append(test.id())


def main() -> int:
    os.chdir(ROOT)
    evidence = ROOT / 'evidence'
    evidence.mkdir(exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    before = time.monotonic()
    syntax_ok = compileall.compile_dir(str(ROOT / 'deepaha_importer'), quiet=1)
    json_paths = list((ROOT / 'examples').glob('*.json')) + list((ROOT / 'schemas').glob('*.json'))
    for path in json_paths:
        json.loads(path.read_text(encoding='utf-8'))
    with (evidence / 'final_verification.log').open('w', encoding='utf-8') as log:
        stream = Tee(sys.stderr, log)
        stream.write(f'Started UTC: {started}\nPython: {sys.version}\nPlatform: {platform.platform()}\n')
        suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), top_level_dir=str(ROOT))
        result = unittest.TextTestRunner(stream=stream, verbosity=2, resultclass=RecordedResult).run(suite)
    optional_versions = {}
    for name in ('fastapi', 'httpx', 'psycopg'):
        try:
            optional_versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            optional_versions[name] = None
    record = {
        'artifact_version': '0.2.0',
        'started_at_utc': started,
        'finished_at_utc': datetime.now(timezone.utc).isoformat(),
        'elapsed_seconds': round(time.monotonic() - before, 3),
        'python_version': platform.python_version(),
        'platform': platform.platform(),
        'display_available': bool(os.environ.get('DISPLAY')),
        'optional_dependencies': optional_versions,
        'syntax_compile': 'PASS' if syntax_ok else 'FAIL',
        'json_parse_files': [str(p.relative_to(ROOT)) for p in json_paths],
        'tests_run': result.testsRun,
        'tests_passed': len(result.passed_ids),
        'tests_failed': len(result.failures),
        'test_errors': len(result.errors),
        'tests_skipped': [{'test': t.id(), 'reason': reason} for t, reason in result.skipped],
        'failures': [{'test': t.id(), 'traceback': detail} for t, detail in result.failures + result.errors],
        'passed_tests': result.passed_ids,
        'review_type': 'AUTHOR_SELF_REVIEW_AND_EXECUTED_TESTS',
        'not_evidenced_by_this_suite': [
            'Native Windows launcher and DPI/font validation',
            'Actual DeepAha repository and existing production schema integration',
            'Actual DeepAha accounts, tenant authorization and source approval',
            'Production HTTPS deployment and production database writes',
            'WMA source consumption or execution',
            'ChatGPT scheduled task Library archiving and cross-run inheritance',
        ],
        'passed': bool(result.wasSuccessful() and syntax_ok),
    }
    (evidence / 'final_verification.json').write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: record[k] for k in ('tests_run', 'tests_passed', 'tests_failed', 'test_errors', 'tests_skipped', 'passed')}, ensure_ascii=False, indent=2))
    return 0 if record['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

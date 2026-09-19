import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from tests.helpers import raw

ROOT = Path(__file__).resolve().parents[1]

class CLITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.file = self.root / 'Handoff.json'
        self.file.write_bytes(raw())

    def run_cli(self, *args, stdin=''):
        return subprocess.run([sys.executable, '-m', 'deepaha_importer', *map(str, args)],
                              cwd=ROOT, input=stdin, text=True, capture_output=True, timeout=15,
                              env={**os.environ, 'PYTHONUTF8': '1'})

    def test_help(self):
        r = self.run_cli('--help'); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('preview', r.stdout)

    def test_validate_without_database(self):
        r = self.run_cli('validate', self.file)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('VALID', r.stdout)

    def test_demo_complete_and_repeat(self):
        args = ('import', self.file, '--demo', '--data-dir', self.root / 'runtime', '--confirm-run', 'demo-20260906-001')
        a = self.run_cli(*args); b = self.run_cli(*args)
        self.assertEqual(a.returncode, 0, a.stderr); self.assertEqual(b.returncode, 0, b.stderr)
        self.assertIn('DEMO_IMPORTED', a.stdout)
        self.assertEqual(len(list((self.root / 'runtime' / 'receipts').glob('*_Receipt.json'))), 1)

    def test_wrong_confirmation(self):
        r = self.run_cli('import', self.file, '--demo', '--data-dir', self.root, '--confirm-run', 'wrong')
        self.assertNotEqual(r.returncode, 0)

    def test_cancel(self):
        r = self.run_cli('import', self.file, '--demo', '--data-dir', self.root, stdin='no\n')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('取消', r.stdout)
        self.assertFalse(list(self.root.rglob('*_Receipt.json')))

    def test_preview_and_separate_commit(self):
        pre = self.root / 'preview.json'
        r = self.run_cli('preview', self.file, '--demo', '--data-dir', self.root / 'runtime', '--output', pre)
        self.assertEqual(r.returncode, 0, r.stderr)
        r = self.run_cli('commit', self.file, '--demo', '--data-dir', self.root / 'runtime', '--preview', pre,
                         '--confirm-run', 'demo-20260906-001')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('DEMO_IMPORTED', r.stdout)

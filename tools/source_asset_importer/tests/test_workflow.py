import json
import tempfile
import unittest
from pathlib import Path
from deepaha_importer.controller import ImportSession
from deepaha_importer.demo import demo_client
from deepaha_importer.receipts import save_receipt
from deepaha_importer.errors import ImporterError
from tests.helpers import raw, handoff


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.file = self.root / 'Handoff.json'; self.file.write_bytes(raw())
        self.client = demo_client(self.root / 'demo')
        self.flow = ImportSession(self.root / 'results')
        self.flow.load(self.file)

    def test_preview_then_confirm_receipt(self):
        self.flow.preview(self.client)
        result = self.flow.commit(True)
        self.assertEqual(result['receipt']['status'], 'DEMO_IMPORTED')
        self.assertTrue(Path(result['json_path']).is_file())
        self.assertTrue(Path(result['markdown_path']).is_file())
        self.assertFalse(result['receipt']['receipt_upload_required'])

    def test_input_changes_invalidate_confirm(self):
        self.flow.preview(self.client)
        d = handoff(); d['warnings'].append('changed'); self.file.write_bytes(raw(d))
        with self.assertRaises(ImporterError) as ctx: self.flow.commit(True)
        self.assertEqual(ctx.exception.code, 'INPUT_CHANGED')

    def test_new_file_invalidates_preview(self):
        self.flow.preview(self.client); self.flow.load(self.file)
        with self.assertRaises(ImporterError): self.flow.commit(True)

    def test_cancel_does_not_submit(self):
        self.flow.preview(self.client)
        with self.assertRaises(ImporterError): self.flow.commit(False)
        with self.assertRaises(ImporterError): self.client.receipt(self.flow.package)

    def test_recover_after_restart(self):
        self.flow.preview(self.client); first = self.flow.commit(True)
        second_flow = ImportSession(self.root / 'results'); second_flow.load(self.file)
        recovered = second_flow.recover(self.client)
        self.assertEqual(first['receipt'], recovered['receipt'])

    def test_no_token_written_into_pending_or_receipts(self):
        preview = self.flow.preview(self.client); token = preview['confirmation_token']
        self.flow.commit(True)
        for f in (self.root / 'results').rglob('*'):
            if f.is_file(): self.assertNotIn(token, f.read_text(encoding='utf-8'))

    def test_demo_receipt_marked_nonproduction(self):
        self.flow.preview(self.client); result = self.flow.commit(True)
        text = Path(result['markdown_path']).read_text(encoding='utf-8')
        self.assertIn('不是正式', text)

    def test_saved_receipt_is_idempotent_and_never_overwrites(self):
        self.flow.preview(self.client); r = self.flow.commit(True)['receipt']
        a = save_receipt(r, self.root / 'extra'); b = save_receipt(r, self.root / 'extra')
        self.assertEqual(a, b)
        r['status'] = 'tampered'
        with self.assertRaises(ImporterError): save_receipt(r, self.root / 'extra')

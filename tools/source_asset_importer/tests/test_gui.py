"""Real Tk/worker/service smoke tests under Xvfb; dialogs only are simulated."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.environ.get('DISPLAY') or sys.platform in ('win32','darwin'), '需要图形显示；可用 xvfb-run 执行')
class GUITests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from deepaha_importer.gui import ImportWindow
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root=tk.Tk(); self.addCleanup(self.root.destroy)
        self.ui=ImportWindow(self.root, Path(self.temp.name))
        self.root.update()

    def wait(self):
        deadline=time.monotonic()+8
        while self.ui.busy and time.monotonic()<deadline:
            self.root.update(); time.sleep(.03)
        self.root.update()
        self.assertFalse(self.ui.busy,'UI worker did not complete')

    def load_preview(self):
        self.ui._sample(); self.wait()
        self.ui._preview(); self.wait()

    def test_initial_confirmation_disabled(self):
        self.assertTrue(self.ui.demo.get())
        self.assertEqual(str(self.ui.commit_button['state']),'disabled')

    def test_real_preview_populates_table(self):
        self.load_preview()
        self.assertEqual(len(self.ui.tree.get_children()),5)
        self.assertEqual(str(self.ui.commit_button['state']),'normal')

    def test_target_change_invalidates_preview(self):
        self.load_preview(); self.ui.server.set('https://example.org')
        self.assertIsNone(self.ui.session.preview_result)
        self.assertEqual(str(self.ui.commit_button['state']),'disabled')

    def test_real_confirm_writes_receipt(self):
        self.load_preview()
        with patch('deepaha_importer.gui.messagebox.askyesno',return_value=True):
            self.ui._commit(); self.wait()
        self.assertIn('DEMO_IMPORTED',self.ui.status.get())
        self.assertEqual(len(list((Path(self.temp.name)/'receipts').glob('*_Receipt.json'))),1)

    def test_cancel_has_no_receipt(self):
        self.load_preview()
        with patch('deepaha_importer.gui.messagebox.askyesno',return_value=False): self.ui._commit()
        self.assertFalse(list(Path(self.temp.name).rglob('*_Receipt.json')))

    def test_action_buttons_visible_at_default_and_minimum_size(self):
        for geometry in ('1100x790','850x620'):
            self.root.geometry(geometry); self.root.update()
            button=self.ui.commit_button
            self.assertTrue(button.winfo_ismapped(),geometry)
            bottom=button.winfo_rooty()+button.winfo_height()
            self.assertLessEqual(bottom,self.root.winfo_rooty()+self.root.winfo_height(),geometry)

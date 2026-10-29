"""Offscreen Qt smoke test; never opens or writes a keyboard."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from test_core import fixture

from ps2avrgb.gui import Window


class QtTests(unittest.TestCase):
    def test_review_undo_and_click_workflow(self):
        _app = QApplication.instance() or QApplication([])  # keep the Qt app alive for the test
        with patch("ps2avrgb.protocol.devices", return_value=[]):
            window = Window()
        window.data = fixture()
        window.baseline = window.data
        window.render()
        self.assertTrue(window.advanced.isHidden())
        with patch.object(window, "pick_key") as picker:
            window.table.setCurrentCell(3, 4)
            window.click_key(3, 4)
            picker.assert_called_once()
        window.key.setCurrentIndex(155)
        window.assign()
        self.assertEqual(len(window.change_lines()), 1)
        self.assertIn("matrix (3, 5)", window.change_lines()[0])
        window.layer.setCurrentIndex(1)
        window.table.setCurrentCell(0, 0)
        window.key.setCurrentIndex(156)
        window.assign()
        self.assertEqual(len(window.change_lines()), 2)
        window.undo_edit()
        self.assertEqual(len(window.change_lines()), 1)
        window.undo_edit()
        self.assertEqual(window.data, window.baseline)
        self.assertFalse(window.undo.isEnabled())
        window.dirty = False
        window.close()

    def test_write_action_uses_shared_backend_worker(self):
        from PySide6.QtWidgets import QMessageBox

        _app = QApplication.instance() or QApplication([])  # keep the Qt app alive for the test
        with patch(
            "ps2avrgb.protocol.devices",
            return_value=[{"path": b"1-1.2.4:1.1", "product_string": "ps2avrGB"}],
        ):
            window = Window()
        window.data = fixture()
        window.render()
        window.dirty = True
        with (
            patch("ps2avrgb.gui.QMessageBox.question", return_value=QMessageBox.Yes),
            patch("ps2avrgb.gui.QThreadPool") as pool,
        ):
            window.flash_keymap()
            pool.globalInstance.return_value.start.assert_called_once_with(window.worker)
            self.assertTrue(window.busy)
            self.assertEqual(window.worker.path, "1-1.2.4:1.1")
        with patch("ps2avrgb.gui.QMessageBox.information"):
            window.flash_finished({"backup": "/tmp/verified-backup.json"})
        self.assertFalse(window.busy)
        self.assertFalse(window.dirty)
        self.assertTrue(window.centralWidget().isEnabled())
        window.close()

    def test_virtual_key_picker(self):
        from ps2avrgb.picker import KeyPicker

        _app = QApplication.instance() or QApplication([])  # keep the Qt app alive for the test
        picker = KeyPicker()
        codes = {code for _, _, code, _ in picker.buttons}
        self.assertTrue(set(range(145, 157)).issubset(codes))
        self.assertTrue(set(range(103, 111)).issubset(codes))
        picker.search.setText("F23")
        candidates = [(code, b) for _, _, code, b in picker.buttons if code == 155]
        self.assertEqual(len(candidates), 1)
        self.assertFalse(candidates[0][1].isHidden())
        candidates[0][1].click()
        self.assertEqual(picker.selected, 155)
        self.assertEqual(picker.result(), 1)

    def test_matrix_and_edits(self):
        _app = QApplication.instance() or QApplication([])  # keep the Qt app alive for the test
        with patch("ps2avrgb.protocol.devices", return_value=[]):
            window = Window()
        window.data = fixture()
        window.render()
        self.assertEqual((window.table.rowCount(), window.table.columnCount()), (4, 6))
        self.assertEqual(window.table.columnSpan(3, 4), 2)
        self.assertEqual(
            sum(window.table.item(r, c) is not None for r in range(4) for c in range(6)), 23
        )
        original_hidden = bytes.fromhex(window.data["keymap"][0])[3 * 8 + 4]
        window.table.setCurrentCell(3, 4)
        window.key.setCurrentIndex(106)
        window.assign()
        self.assertEqual(bytes.fromhex(window.data["keymap"][0])[3 * 8 + 5], 106)
        self.assertEqual(bytes.fromhex(window.data["keymap"][0])[3 * 8 + 4], original_hidden)
        window.select(3, 4)
        self.assertEqual(window.key.currentData(), 106)
        window.view.setCurrentIndex(1)
        self.assertEqual((window.table.rowCount(), window.table.columnCount()), (15, 8))
        self.assertEqual(window.table.columnSpan(3, 4), 1)
        window.table.setCurrentCell(0, 0)
        window.key.setCurrentIndex(145)
        window.assign()
        self.assertEqual(bytes.fromhex(window.data["keymap"][0])[0], 145)
        window.key.setEditText("F24")
        window.assign()
        self.assertEqual(bytes.fromhex(window.data["keymap"][0])[0], 156)
        window.dirty = False
        window.close()


if __name__ == "__main__":
    unittest.main()

import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
from quadview.core.browser_setup import configure_manual_fullscreen, offer_first_run_setup, SETTING

class BrowserSetupTests(unittest.TestCase):
    def test_decline_is_remembered_without_changing_browser(self):
        from PySide6.QtWidgets import QMessageBox
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.No) as ask:
                with patch('quadview.core.browser_setup.configure_manual_fullscreen') as configure:
                    offer_first_run_setup(None, Path(directory))
                    offer_first_run_setup(None, Path(directory))
                    ask.assert_called_once()
                    configure.assert_not_called()

    def test_accept_applies_setup_and_force_can_reopen_it(self):
        from PySide6.QtWidgets import QMessageBox
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
                with patch('quadview.core.browser_setup.configure_manual_fullscreen') as configure:
                    offer_first_run_setup(None, Path(directory))
                    offer_first_run_setup(None, Path(directory), force=True)
                    self.assertEqual(configure.call_count, 2)
    def test_preserves_other_overrides_and_backs_up_exact_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'librewolf.overrides.cfg'
            original = b'// existing\r\npref("other.setting", 123);'
            path.write_bytes(original)
            self.assertTrue(configure_manual_fullscreen(path))
            self.assertTrue(path.read_bytes().startswith(original + b'\r\n'))
            self.assertEqual(path.with_name(path.name + '.quadview-backup').read_bytes(), original)
            self.assertIn(SETTING, path.read_text())
            self.assertFalse(configure_manual_fullscreen(path))
            self.assertEqual(path.read_text().count(SETTING), 1)

    def test_creates_missing_override_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'missing' / 'librewolf.overrides.cfg'
            self.assertTrue(configure_manual_fullscreen(path))
            self.assertIn(SETTING, path.read_text())

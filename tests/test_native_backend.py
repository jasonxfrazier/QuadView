"""Native API contracts. These tests do not open or modify desktop windows."""

import sys
import unittest
from unittest.mock import patch


@unittest.skipUnless(sys.platform == "win32", "Windows API adapter")
class NativeContracts(unittest.TestCase):
    def setUp(self):
        from quadview.core.browser_manager import BrowserManager
        from quadview.core.window_manager import WindowManager
        self.browser = BrowserManager()
        self.windows = WindowManager()

    def test_command_preserves_normal_profile_and_uses_argument_list(self):
        with patch.object(self.browser, "validate_executable", return_value=r"C:\LibreWolf\librewolf.exe"):
            with patch("quadview.core.browser_manager.subprocess.Popen") as process:
                self.browser.launch("configured path", "https://example.com/?one=1&two=2")
        args, kwargs = process.call_args
        self.assertEqual(args[0], [r"C:\LibreWolf\librewolf.exe", "--new-window", "https://example.com/?one=1&two=2"])
        self.assertFalse(kwargs["shell"])

    def test_win_event_generation_changes_when_handle_is_reused(self):
        self.windows._on_event(0, 0x8000, 123, 0, 0, 0, 0)
        old = self.windows._generations[123]
        self.windows._on_event(0, 0x8002, 123, 0, 0, 0, 0)
        self.assertEqual(self.windows._generations[123], old)
        self.windows._on_event(0, 0x8000, 123, 0, 0, 0, 0)
        self.assertEqual(self.windows._generations[123], old)
        self.windows._on_event(0, 0x8001, 123, 0, 0, 0, 0)
        self.assertNotIn(123, self.windows._generations)
        self.windows._on_event(0, 0x8000, 123, 0, 0, 0, 0)
        self.assertGreater(self.windows._generations[123], old)

    def test_window_closure_refuses_stale_identity(self):
        from quadview.core.models import ProcessIdentity, WindowSnapshot
        record = WindowSnapshot(123, ProcessIdentity(42, 100, "librewolf.exe"), 1)
        with patch.object(self.windows, "identity_alive", return_value=False):
            with patch("quadview.core.window_manager.win32gui.PostMessage") as post:
                with self.assertRaises(RuntimeError):
                    self.windows.close(record)
        post.assert_not_called()

    def test_closure_posts_wm_close_only(self):
        from quadview.core.models import ProcessIdentity, WindowSnapshot
        import win32con
        record = WindowSnapshot(123, ProcessIdentity(42, 100, "librewolf.exe"), 1)
        with patch.object(self.windows, "identity_alive", return_value=True):
            with patch("quadview.core.window_manager.win32gui.PostMessage") as post:
                self.windows.close(record)
        post.assert_called_once_with(123, win32con.WM_CLOSE, 0, 0)


if __name__ == "__main__":
    unittest.main()

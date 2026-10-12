"""Session policy tests using deterministic fake native adapters."""

import unittest

from quadview.core.models import AppConfig, Monitor, ProcessIdentity, Rect, SessionState, WindowSnapshot
from quadview.core.session_manager import RUNNING_MESSAGE, SessionError, SessionManager

PROCESS = ProcessIdentity(42, 116444736000001000, "librewolf.exe")
MONITOR = Monitor("display", "Display", Rect(-1001, 0, 0, 701), Rect(-1001, 0, 0, 741), True)


class FakeClock:
    now = 0.0
    on_sleep = None

    def monotonic(self):
        return self.now

    def sleep(self, amount):
        self.now += amount
        if self.on_sleep:
            self.on_sleep()


class FakeWindows:
    def __init__(self):
        self.windows = []
        self.displays = [MONITOR]
        self.placed = []
        self.closed = []
        self.started = False
        self.refuse_close = False
        self.fail_place = False
        self.fullscreen_result = "entered"
        self.fullscreen_requests = []

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def monitors(self):
        return self.displays

    def enumerate_windows(self, executable):
        return self.windows.copy()

    def identity_alive(self, window):
        return window in self.windows

    def place(self, window, rect):
        if self.fail_place:
            raise RuntimeError("Browser minimum size prevents layout.")
        self.placed.append((window, rect))
        return rect

    def close(self, window):
        self.closed.append(window)
        if not self.refuse_close:
            self.windows.remove(window)

    def bounds(self, window):
        return next(rect for found, rect in reversed(self.placed) if found == window)

    def fullscreen(self, window, cancelled, *, exit_fullscreen=False):
        self.fullscreen_requests.append(window)
        return "exited" if exit_fullscreen else self.fullscreen_result


class FakeBrowser:
    def __init__(self, windows):
        self.windows = windows
        self.running = False
        self.requests = []
        self.on_launch = None

    def validate_executable(self, path):
        if not path:
            raise ValueError("Select LibreWolf.")
        return path

    def running_processes(self):
        return [PROCESS] if self.running else []

    def launch(self, executable, url):
        self.requests.append(url)
        if self.on_launch:
            self.on_launch()
        else:
            self.windows.windows.append(WindowSnapshot(100 + len(self.requests), PROCESS, len(self.requests)))


class SessionTests(unittest.TestCase):
    def test_launch_never_activates_player_controls(self):
        self.session.launch(self.config)
        self.assertEqual(self.windows.fullscreen_requests, [])
        self.assertEqual(self.session.state, SessionState.ACTIVE)

    def test_launch_and_reapply_for_one_through_four_selected_links(self):
        from quadview.core.layout_manager import regions_for_count
        for count in range(1, 5):
            with self.subTest(count=count):
                self.setUp()
                self.config.urls = self.config.urls[:count]
                self.session.launch(self.config)
                self.assertEqual(len(self.session.managed), count)
                self.assertEqual([rect for _window, rect in self.windows.placed], list(regions_for_count(MONITOR.work_area, count)))
                self.windows.placed.clear()
                self.session.reapply()
                self.assertEqual([rect for _window, rect in self.windows.placed], list(regions_for_count(MONITOR.work_area, count)))
                self.session.close()

    def test_manual_close_reflows_remaining_windows_without_adopting_unmanaged(self):
        self.session.launch(self.config)
        self.windows.windows.pop(1)
        self.windows.placed.clear()
        self.session.refresh()
        self.assertEqual(self.windows.placed[0][1], Rect(-1001, 0, -501, 701))
        self.assertEqual(len(self.windows.placed), 3)

    def test_zero_five_and_duplicate_selections_are_rejected_before_browser_launch(self):
        for urls in ([], ["a.example"] * 5, ["a.example", "https://a.example"]):
            self.config.urls = urls
            with self.assertRaises(SessionError):
                self.session.launch(self.config)
        self.assertEqual(self.browser.requests, [])

    def setUp(self):
        self.windows = FakeWindows()
        self.browser = FakeBrowser(self.windows)
        self.clock = FakeClock()
        self.updates = []
        self.session = SessionManager(
            self.browser, self.windows, self.updates.append,
            launch_timeout=1, close_timeout=0.5, settle_time=0.2, poll_interval=0.1,
            monotonic=self.clock.monotonic, sleep=self.clock.sleep, wall_time_ns=lambda: 0,
        )
        self.config = AppConfig(urls=["one.example", "http://two.example", "three.example", "four.example"], executable_path="librewolf.exe", monitor_id="display")

    def test_launch_assigns_sequential_requests_and_exact_rectangles(self):
        self.session.launch(self.config)
        self.assertEqual(self.browser.requests, ["https://one.example", "http://two.example", "https://three.example", "https://four.example"])
        self.assertEqual([item.quadrant for item in self.session.managed], [0, 1, 2, 3])
        self.assertEqual(self.windows.placed[3][1], Rect(-501, 350, 0, 701))
        self.assertEqual(self.session.state, SessionState.ACTIVE)
        self.assertEqual(self.updates[0].state, SessionState.VALIDATING)

    def test_existing_background_browser_prevents_any_launch(self):
        self.browser.running = True
        with self.assertRaisesRegex(SessionError, "completely closed") as caught:
            self.session.launch(self.config)
        self.assertEqual(str(caught.exception), RUNNING_MESSAGE)
        self.assertEqual(self.browser.requests, [])
        self.assertFalse(self.windows.started)

    def test_invalid_url_does_not_launch_browser(self):
        self.config.urls[2] = "javascript:alert(1)"
        with self.assertRaises(ValueError):
            self.session.launch(self.config)
        self.assertEqual(self.browser.requests, [])

    def test_multiple_candidates_are_never_adopted_or_moved(self):
        def appear():
            self.windows.windows.extend([WindowSnapshot(1, PROCESS, 1), WindowSnapshot(2, PROCESS, 2)])
        self.browser.on_launch = appear
        with self.assertRaisesRegex(SessionError, "More than one"):
            self.session.launch(self.config)
        self.assertEqual(self.session.managed, [])
        self.assertEqual(self.windows.placed, [])
        self.session.close()
        self.assertEqual(len(self.windows.windows), 2)

    def test_browser_startup_timeout_leaves_unassociated_windows_alone(self):
        self.browser.on_launch = lambda: None
        with self.assertRaisesRegex(SessionError, "in time"):
            self.session.launch(self.config)
        self.assertEqual(self.session.state, SessionState.ERROR)
        self.assertEqual(self.windows.closed, [])

    def test_layout_failure_retains_partial_session_for_explicit_close(self):
        self.windows.fail_place = True
        with self.assertRaises(RuntimeError):
            self.session.launch(self.config)
        self.assertEqual(len(self.session.managed), 1)
        self.assertEqual(self.windows.closed, [])
        self.session.close()
        self.assertEqual(len(self.windows.closed), 1)
        self.assertEqual(self.session.state, SessionState.IDLE)

    def test_manual_close_does_not_shift_other_quadrants_or_adopt_new_windows(self):
        self.session.launch(self.config)
        self.windows.windows.pop(1)
        unmanaged = WindowSnapshot(999, PROCESS, 999)
        self.windows.windows.append(unmanaged)
        self.session.refresh()
        self.windows.placed.clear()
        self.session.reapply()
        self.assertEqual([item.quadrant for item in self.session.managed], [0, 2, 3])
        self.assertEqual(len(self.windows.placed), 3)
        self.session.close()
        self.assertEqual(self.windows.windows, [unmanaged])

    def test_reused_handle_is_retired_even_with_same_process(self):
        self.session.launch(self.config)
        old = self.windows.windows[0]
        replacement = WindowSnapshot(old.hwnd, old.process, 999)
        self.windows.windows[0] = replacement
        self.session.refresh()
        self.session.close()
        self.assertEqual(self.windows.windows, [replacement])

    def test_close_prompt_timeout_retains_owned_windows_and_allows_retry(self):
        self.session.launch(self.config)
        self.windows.refuse_close = True
        with self.assertRaisesRegex(SessionError, "confirmation dialogs"):
            self.session.close()
        self.assertEqual(len(self.session.managed), 4)
        self.windows.refuse_close = False
        self.session.close()
        self.assertEqual(self.session.state, SessionState.IDLE)

    def test_monitor_disconnection_stops_launch(self):
        self.clock.on_sleep = lambda: self.windows.displays.clear()
        with self.assertRaisesRegex(SessionError, "monitor is no longer"):
            self.session.launch(self.config)
        self.assertEqual(self.windows.placed, [])

    def test_process_predating_session_is_rejected(self):
        previous = ProcessIdentity(41, 116444735999999999, "librewolf.exe")
        self.browser.on_launch = lambda: self.windows.windows.append(WindowSnapshot(1, previous, 1))
        with self.assertRaisesRegex(SessionError, "predates"):
            self.session.launch(self.config)
        self.assertEqual(self.session.managed, [])

    def test_later_window_from_different_process_is_rejected(self):
        other = ProcessIdentity(43, PROCESS.created_at + 1, "librewolf.exe")
        def appear():
            count = len(self.browser.requests)
            self.windows.windows.append(WindowSnapshot(count, PROCESS if count == 1 else other, count))
        self.browser.on_launch = appear
        with self.assertRaisesRegex(SessionError, "different LibreWolf process"):
            self.session.launch(self.config)
        self.assertEqual(len(self.session.managed), 1)
        self.session.close()
        self.assertEqual(len(self.windows.windows), 1)

    def test_cancellation_leaves_browser_open_and_observer_shutdown_requires_idle_worker(self):
        self.clock.on_sleep = self.session.cancel
        with self.assertRaisesRegex(SessionError, "cancelled"):
            self.session.launch(self.config)
        self.assertEqual(self.windows.closed, [])
        self.session._operation.acquire()
        with self.assertRaises(SessionError):
            self.session.shutdown()
        self.session._operation.release()
        self.session.shutdown()
        self.assertFalse(self.windows.started)
        self.assertEqual(len(self.windows.windows), 1)

    def test_shutdown_does_not_close_active_browser_windows(self):
        self.session.launch(self.config)
        self.session.shutdown()
        self.assertEqual(len(self.windows.windows), 4)
        self.assertEqual(self.windows.closed, [])


if __name__ == "__main__":
    unittest.main()

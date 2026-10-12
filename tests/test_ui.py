"""Offscreen UI checks; these never launch or modify a real browser."""

from __future__ import annotations

import os
from pathlib import Path
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QFontDatabase
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from quadview.core.models import AppConfig, Monitor, Rect, SessionState, SessionUpdate
from quadview.ui.main_window import MainWindow
from quadview.ui.session_worker import SessionWorker


MONITOR = Monitor("test-display", "Test monitor", Rect(0, 0, 1920, 1040), Rect(0, 0, 1920, 1080), True)
EXECUTABLE = r"C:\Program Files\LibreWolf\librewolf.exe"


class MemoryStore:
    last_warning = None

    def __init__(self) -> None:
        self.saved: list[AppConfig] = []

    def save(self, config: AppConfig) -> None:
        self.saved.append(config)


class FakeBrowser:
    def detect_executable(self, saved: str) -> str:
        return saved or EXECUTABLE

    def running_processes(self) -> list[object]:
        return []


class FakeWindows:
    def monitors(self) -> list[Monitor]:
        return [MONITOR]


class FakeSession:
    def __init__(self, notify: object, events: list[tuple[str, int]]) -> None:
        self.browser = FakeBrowser()
        self.windows = FakeWindows()
        self.managed: list[object] = []
        self.state = SessionState.IDLE
        self.notify = notify
        self.events = events
        self.started = threading.Event()
        self.cancelled = threading.Event()
        self.received_config: AppConfig | None = None
        events.append(("constructed", threading.get_ident()))

    def launch(self, config: AppConfig) -> None:
        self.received_config = config
        self.events.append(("launch_started", threading.get_ident()))
        self.state = SessionState.LAUNCHING
        self.notify(SessionUpdate(self.state, "Launching window 1 of 4", 0))
        self.started.set()
        if not self.cancelled.wait(2):
            raise RuntimeError("The test launch did not receive cancellation.")
        self.events.append(("launch_ended", threading.get_ident()))

    def cancel(self) -> None:
        self.events.append(("cancel", threading.get_ident()))
        self.cancelled.set()

    def refresh(self) -> None:
        pass

    def shutdown(self) -> None:
        self.events.append(("shutdown", threading.get_ident()))


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])
        # The Windows offscreen plugin does not discover system fonts itself.
        for filename in ("segoeui.ttf", "seguisb.ttf"):
            path = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / filename
            if path.is_file():
                QFontDatabase.addApplicationFont(str(path))

    def setUp(self) -> None:
        self.windows: list[MainWindow] = []

    def tearDown(self) -> None:
        for window in self.windows:
            window._begin_exit()
            self.pump_until(lambda: not window._thread.isRunning(), 3)
            window.deleteLater()
        self.app.processEvents()

    def pump_until(self, predicate: object, timeout: float = 2) -> None:
        deadline = time.monotonic() + timeout
        while not predicate() and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(0.005)
        self.app.processEvents()
        self.assertTrue(predicate(), "The queued UI operation did not finish in time.")

    def window(self, config: AppConfig | None = None, **kwargs: object) -> tuple[MainWindow, MemoryStore]:
        store = MemoryStore()
        result = MainWindow(store, config or AppConfig(), **kwargs)
        self.windows.append(result)
        return result, store

    @staticmethod
    def inspect(window: MainWindow) -> None:
        window._on_completed("inspect", {
            "monitors": [MONITOR], "executable": EXECUTABLE,
            "requested_executable": window.executable_input.text(), "running": False,
        }, "")

    def test_invalid_source_edit_preserves_previous_source_without_credentials(self) -> None:
        config = AppConfig(source_url="https://page.example/streams", urls=["https://stream.example/one"])
        window, store = self.window(config, start_worker=False)
        window.source_input.setText("https://user:secret@example.com")
        window._save_settings()
        self.assertEqual(store.saved[-1].source_url, config.source_url)
        window._fetch()
        self.assertIn("usernames", window.message_label.text())
        self.assertTrue(window.source_input.property("invalid"))
        self.assertIsNone(window._inflight)
        self.assertNotIn("secret", window.message_label.text())

    def test_default_page_has_no_automatic_fullscreen_option(self) -> None:
        window, store = self.window(start_worker=False)
        self.assertEqual(window.source_input.text(), "https://crackstreams.mx/league/nflstreams")
        self.assertFalse(hasattr(window, "fullscreen_checkbox"))

    def test_inspection_keeps_saved_urls_and_reports_monitor_fallback(self) -> None:
        config = AppConfig(urls=["https://one.example", "https://site.example/stream/stream-one", "https://site.example/STREAM-two"], monitor_id="removed-display")
        window, store = self.window(config, start_worker=False)
        self.assertEqual(store.saved, [])
        self.inspect(window)
        self.assertEqual(window._selected_urls, [])
        self.assertEqual(window.link_list.count(), 0)
        self.assertFalse(window.launch_button.isEnabled())
        self.assertEqual(window._collect_config().urls, [])
        self.assertIn("unavailable", window.notice_label.text())
        self.assertEqual(window.monitor_combo.currentData(), MONITOR)

    def test_selection_limit_and_click_order_determine_priority(self) -> None:
        window, _store = self.window(start_worker=False)
        window._set_available_links({f"Stream {index}": f"https://site.example/stream/stream-{index}" for index in range(6)})
        for index in (3, 0, 2, 4, 5):
            window.link_list.item(index).setCheckState(Qt.CheckState.Checked)
        self.assertEqual(window._selected_urls, [f"https://site.example/stream/stream-{index}" for index in (3, 0, 2, 4)])
        self.assertEqual(window.link_list.item(5).checkState(), Qt.CheckState.Unchecked)
        self.assertTrue(window.link_list.item(3).text().startswith("1 ·"))
        window.link_list.item(0).setCheckState(Qt.CheckState.Unchecked)
        self.assertIn("Priority left", window.layout_label.text())
        self.assertEqual(window._collect_config().urls, [f"https://site.example/stream/stream-{index}" for index in (3, 2, 4)])

    def test_fetch_empty_result_clears_stale_selection_and_failure_retains_it(self) -> None:
        window, _store = self.window(AppConfig(urls=["https://site.example/stream/stream-one"]), start_worker=False)
        window._on_completed("fetch", {"Stream One": "https://site.example/stream/stream-one"}, "")
        window.link_list.item(0).setCheckState(Qt.CheckState.Checked)
        window._on_completed("fetch", None, "Could not fetch links.")
        self.assertEqual(len(window._selected_urls), 1)
        window._on_completed("fetch", {}, "")
        self.assertEqual(window._selected_urls, [])
        self.assertEqual(window.link_list.count(), 0)
        self.assertIn("No visible", window.message_label.text())

    def test_every_fetch_clears_previous_and_saved_selection_but_keeps_exact_names(self) -> None:
        url = "https://site.example/stream/stream-one?key=a-b"
        window, _store = self.window(AppConfig(urls=[url]), start_worker=False)
        window._on_completed("fetch", {"Stream One?Key=A B": url}, "")
        self.assertEqual(window.link_list.item(0).text(), "Stream One?Key=A B")
        self.assertEqual(window._selected_urls, [])
        window.link_list.item(0).setCheckState(Qt.CheckState.Checked)
        window._on_completed("fetch", {"Stream One?Key=A B": url}, "")
        self.assertEqual(window._selected_urls, [])
        self.assertEqual(window.link_list.item(0).checkState(), Qt.CheckState.Unchecked)

    def test_picker_filters_every_result_by_url_and_preserves_original_splitting(self) -> None:
        window, _store = self.window(start_worker=False)
        window._on_completed("fetch", {
            "Stream-looking title": "https://site.example/news",
            "Uppercase": "https://site.example/STREAM-one",
            "Wrong supplied title": "https://site.example/stream/stream-one?next=/other-channel",
            "Old collision": "https://first.example/stream/same-name",
            "New collision": "https://last.example/stream/same-name",
        }, "")
        self.assertEqual(window.link_list.count(), 2)
        self.assertEqual(window.link_list.item(0).text(), "Other Channel")
        self.assertEqual(window.link_list.item(1).text(), "Same Name")
        self.assertEqual(window.link_list.item(1).data(Qt.ItemDataRole.UserRole), "https://last.example/stream/same-name")
        self.assertEqual(window._selected_urls, [])

    def test_actual_unwanted_league_url_is_excluded_in_picker_and_saved_choices(self) -> None:
        league = "https://crackstreams.mx/league/nflstreams"
        game = "https://crackstreams.mx/stream/buffalo-bills-vs-los-angeles-rams"
        window, _store = self.window(AppConfig(urls=[league, game]), start_worker=False)
        self.assertEqual(window._selected_urls, [])
        window._on_completed("fetch", {"NFL": league, "Game": game}, "")
        self.assertEqual(window.link_list.count(), 1)
        self.assertEqual(window.link_list.item(0).text(), "Buffalo Bills Vs Los Angeles Rams")
        self.assertEqual(window._selected_urls, [])

    def test_saved_stream_choices_are_shown_only_if_a_fresh_fetch_contains_them(self) -> None:
        window, _store = self.window(AppConfig(urls=["https://site.example/stream/stream-old"]), start_worker=False)
        self.assertEqual(window.link_list.count(), 0)
        window._on_completed("fetch", {"Stream New": "https://site.example/stream/stream-new"}, "")
        self.assertEqual(window.link_list.count(), 1)
        self.assertEqual(window._selected_urls, [])
        self.assertEqual(window._collect_config().urls, [])

    def test_geometry_clamped_and_status_stays_visible_on_short_window(self) -> None:
        window, _store = self.window(AppConfig(window_geometry=Rect(9000, 9000, 9600, 9800)), start_worker=False)
        self.assertTrue(any(screen.availableGeometry().contains(window.geometry()) for screen in self.app.screens()))
        self.inspect(window)
        window.resize(window.width(), 480)
        window.show()
        self.app.processEvents()
        bottom = window.mapFromGlobal(window.message_label.mapToGlobal(window.message_label.rect().bottomRight()))
        self.assertLess(bottom.y(), window.height())
        self.assertTrue(window.close_session_button.isVisible())

    def test_worker_preserves_actionable_native_error(self) -> None:
        class BrokenWindows(FakeWindows):
            def monitors(self) -> list[Monitor]:
                raise RuntimeError("LibreWolf could not fit the requested quadrant.")

        def factory(notify: object) -> FakeSession:
            session = FakeSession(notify, [])
            session.windows = BrokenWindows()
            return session

        worker = SessionWorker(factory)
        completed: list[tuple[str, object, str]] = []
        worker.completed.connect(lambda command, result, error: completed.append((command, result, error)))
        worker.perform("inspect", AppConfig())
        self.assertEqual(completed[0][2], "LibreWolf could not fit the requested quadrant.")
        worker.deleteLater()

    def test_exit_cancels_launch_then_shuts_down_on_worker_thread(self) -> None:
        events: list[tuple[str, int]] = []
        sessions: list[FakeSession] = []

        def factory(notify: object) -> FakeSession:
            session = FakeSession(notify, events)
            sessions.append(session)
            return session

        window, _store = self.window(
            AppConfig(urls=["https://site.example/stream/stream-one", "http://site.example/stream/stream-two", "https://site.example/stream/stream-three", "https://site.example/stream/stream-four"]),
            worker=SessionWorker(factory),
        )
        self.pump_until(lambda: window.monitor_combo.currentData() == MONITOR and window._inflight is None)
        window._on_completed("fetch", {url: url for url in window.config.urls}, "")
        for index in range(window.link_list.count()):
            window.link_list.item(index).setCheckState(Qt.CheckState.Checked)
        window._launch()
        self.pump_until(lambda: bool(sessions) and sessions[0].started.is_set())
        window._begin_exit()
        self.pump_until(lambda: not window._thread.isRunning())
        self.assertEqual([name for name, _thread in events], ["constructed", "launch_started", "cancel", "launch_ended", "shutdown"])
        main_thread = threading.get_ident()
        self.assertTrue(all(ident != main_thread for name, ident in events if name != "cancel"))
        self.assertEqual(next(ident for name, ident in events if name == "cancel"), main_thread)
        self.assertEqual(sessions[0].received_config.urls, ["https://site.example/stream/stream-one", "http://site.example/stream/stream-two", "https://site.example/stream/stream-three", "https://site.example/stream/stream-four"])
        self.assertNotIn("close", [name for name, _thread in events])

    def test_starting_fetch_clears_checks_even_if_fetch_later_fails(self) -> None:
        window, _store = self.window(start_worker=False)
        url = "https://site.example/stream/game"
        window._set_available_links({"Game": url})
        window.link_list.item(0).setCheckState(Qt.CheckState.Checked)
        window._fetch()
        window._on_completed("fetch", None, "Could not fetch links.")
        self.assertEqual(window._selected_urls, [])
        self.assertEqual(window.link_list.item(0).checkState(), Qt.CheckState.Unchecked)


if __name__ == "__main__":
    unittest.main()

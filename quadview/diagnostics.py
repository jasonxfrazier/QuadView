"""Opt-in desktop prototype. Normal invocation only inspects the environment.

The --smoke flag opens one through four public test pages (--count defaults to 4)
and arranges their native windows.
--close requests normal closure of only those managed test windows afterwards.
No profile files, browser settings, or page contents are inspected or changed.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import time

from .core.models import AppConfig


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Launch and arrange four browser test windows.")
    parser.add_argument("--close", action="store_true", help="Gracefully close managed smoke-test windows afterwards.")
    parser.add_argument("--exercise", action="store_true", help="Also test every monitor, minimize/maximize recovery and manual window closure.")
    parser.add_argument("--count", type=int, choices=range(1, 5), default=4, help="Number of windows for the smoke test.")
    parser.add_argument("--output", type=Path, help="Save the diagnostic report as JSON.")
    args = parser.parse_args()
    from .core.browser_manager import BrowserManager
    from .core.window_manager import WindowManager, configure_dpi_awareness
    from .core.session_manager import RUNNING_MESSAGE, SessionError, SessionManager
    configure_dpi_awareness()
    browser, windows = BrowserManager(), WindowManager()
    report: dict = {"fullscreen": "not tested", "profile_files_modified_by_quadview": False}
    session = SessionManager(browser, windows)
    try:
        executable = browser.detect_executable()
        monitors = windows.monitors()
        report.update(executable=executable, monitors=[asdict(m) for m in monitors], running_process_count=len(browser.running_processes()))
        if args.smoke:
            if not executable or not monitors:
                raise RuntimeError("LibreWolf and a connected monitor are required.")
            config = AppConfig(
                urls=["https://example.com", "https://www.python.org", "https://www.mozilla.org", "https://librewolf.net"][:args.count],
                executable_path=executable, monitor_id=monitors[0].identifier,
            )
            session.launch(config)
            report["launch"] = "passed"
            report["windows"] = [
                {"quadrant": item.quadrant + 1, "hwnd": item.window.hwnd, "pid": item.window.process.pid, "bounds": asdict(windows.bounds(item.window))}
                for item in session.managed
            ]
            session.reapply()
            report["reapply"] = "passed"
            second = SessionManager(browser, windows)
            try:
                second.launch(config)
            except SessionError as error:
                report["running_browser_refusal"] = "passed" if str(error) == RUNNING_MESSAGE else "failed"
            else:
                raise RuntimeError("Running-browser refusal failed.")
            if args.exercise:
                import win32con
                import win32gui
                from .core.layout_manager import regions_for_count
                layouts = []
                for monitor in monitors:
                    session.reapply(monitor.identifier)
                    measured = [windows.bounds(item.window) for item in session.managed]
                    if measured != list(regions_for_count(monitor.work_area, args.count)):
                        raise RuntimeError("A monitor layout did not match the requested bounds.")
                    layouts.append({"work_area": asdict(monitor.work_area), "bounds": [asdict(rect) for rect in measured]})
                report["all_monitor_layouts"] = layouts
                first = session.managed[0].window
                for label, mode in (("minimize_recovery", win32con.SW_MINIMIZE), ("maximize_recovery", win32con.SW_MAXIMIZE)):
                    if not windows.identity_alive(first):
                        raise RuntimeError("Test window identity changed.")
                    win32gui.ShowWindow(first.hwnd, mode)
                    time.sleep(0.2)
                    session.reapply()
                    report[label] = "passed"
                if args.count > 1:
                    windows.close(session.managed[1].window)
                    for _ in range(30):
                        time.sleep(0.1)
                        session.refresh()
                        if len(session.managed) == args.count - 1:
                            break
                    expected_indices = [index for index in range(args.count) if index != 1]
                    if [item.quadrant for item in session.managed] != expected_indices:
                        raise RuntimeError("Manual window closure did not preserve remaining selection order.")
                    session.reapply()
                    report["manual_close_reconciliation"] = "passed"
    except Exception as error:
        report["error"] = str(error)
    finally:
        if args.close and session.managed:
            try:
                session.close()
                report["graceful_close"] = "passed"
            except Exception as error:
                report["close_error"] = str(error)
        session.shutdown()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 1 if "error" in report or "close_error" in report else 0


if __name__ == "__main__":
    raise SystemExit(main())

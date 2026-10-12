"""Application startup. No browser is launched until the user clicks Launch."""

from __future__ import annotations

import sys


def main() -> int:
    if sys.platform != "win32":
        print("QuadView requires Windows 10 or 11 and an existing LibreWolf installation.", file=sys.stderr)
        return 1
    try:
        from .core.window_manager import configure_dpi_awareness
        configure_dpi_awareness()
        from PySide6.QtCore import QLockFile
        from PySide6.QtWidgets import QApplication, QMessageBox
        from .core.config_manager import ConfigManager
        from .ui.main_window import MainWindow, make_icon
        from .utils.logging import configure_logging
    except ImportError:
        print("QuadView dependencies are missing. Run 'uv sync' in the project directory.", file=sys.stderr)
        return 1
    app = QApplication(sys.argv)
    app.setApplicationName("QuadView")
    app.setOrganizationName("QuadView")
    app.setWindowIcon(make_icon())
    app.setQuitOnLastWindowClosed(False)
    config_manager = ConfigManager()
    try:
        config_manager.path.parent.mkdir(parents=True, exist_ok=True)
        lock = QLockFile(str(config_manager.path.parent / "quadview.lock"))
        lock.setStaleLockTime(0)
        if not lock.tryLock(0):
            QMessageBox.information(None, "QuadView is already open", "Open the existing QuadView window or its system tray icon.")
            return 0
        configure_logging(config_manager.path.parent / "logs")
        window = MainWindow(config_manager, config_manager.load())
        window.show()
        result = app.exec()
        lock.unlock()
        return result
    except OSError:
        QMessageBox.critical(None, "QuadView settings", "QuadView could not access its local settings directory. Check your user folder permissions.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

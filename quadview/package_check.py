"""Release verification using a disposable local fixture and controller."""
import json
from pathlib import Path
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

def run_check(report_path: str) -> int:
    report = {'frozen': bool(getattr(sys, 'frozen', False))}
    try:
        from PySide6.QtWidgets import QApplication
        from .core.window_manager import configure_dpi_awareness, WindowManager
        from .core.config_manager import ConfigManager
        from .core.models import AppConfig
        from .core.link_discovery import get_links, extract_good_links
        from .ui.main_window import MainWindow
        configure_dpi_awareness()
        app = QApplication([])
        window = MainWindow(ConfigManager(Path(report_path).with_suffix('.config.json')), AppConfig(), start_worker=False)
        window.show()
        app.processEvents()
        report['ui'] = window.isVisible()
        report['monitors'] = len(WindowManager().monitors())
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(b'<a href="/stream/test-game">Game</a><a href="/league/nflstreams">League</a><a href="/stream/hidden" style="display:none">Hidden</a>')
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            good = extract_good_links(get_links(f'http://127.0.0.1:{server.server_port}/'))
            report['bundled_browser_and_filter'] = list(good) == ['Test Game']
            assert report['bundled_browser_and_filter']
        finally:
            server.shutdown()
            window.hide()
            if window._tray:
                window._tray.hide()
        report['status'] = 'passed'
    except Exception as error:
        report.update(status='failed', error=repr(error))
    Path(report_path).write_text(json.dumps(report, indent=2), encoding='utf-8')
    return 0 if report['status'] == 'passed' else 1

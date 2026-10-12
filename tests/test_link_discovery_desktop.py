"""Opt-in browser integration against a temporary local test fixture.

Run with QUADVIEW_DESKTOP_TESTS=1. This opens a disposable Chromium window.
The local HTTP server exists only for the test and is shut down afterwards.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import threading
import unittest

from quadview.core.link_discovery import extract_good_links, get_links

PAGE = b"""<!doctype html><html><head><base href="https://site.example/"></head>
<body>
<a href="stream/stream-one">one</a>
<a href="stream/stream-one">duplicate</a>
<a href="https://other.example/stream/stream-two">two</a>
<a href="hidden-stream" style="display:none">hidden</a>
<a href="transparent-stream" style="opacity:0">transparent</a>
<a href="invisible-stream" style="visibility:hidden">invisible</a>
<a href="mailto:stream@example.com">email</a>
<a href="javascript:void(0)">script</a>
<a href="not-a-channel">filtered by stream rule</a>
<div style="height:2000px"></div><a href="stream/stream-below-fold">below fold</a>
</body></html>"""


class FixtureHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(PAGE)))
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *_args):
        pass


@unittest.skipUnless(os.environ.get("QUADVIEW_DESKTOP_TESTS") == "1", "Opt-in: opens Chromium")
class DesktopLinkDiscoveryTests(unittest.TestCase):
    def test_real_browser_visibility_absolute_hrefs_deduplication_and_stream_names(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            links = get_links(f"http://127.0.0.1:{server.server_port}/")
            self.assertEqual(links, [
                "https://site.example/stream/stream-one",
                "https://other.example/stream/stream-two",
                "https://site.example/not-a-channel",
                "https://site.example/stream/stream-below-fold",
            ])
            self.assertEqual(extract_good_links(links), {
                "Stream One": links[0], "Stream Two": links[1], "Stream Below Fold": links[3],
            })
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

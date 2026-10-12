"""Exact user-supplied stream naming and resource cleanup contracts."""

import unittest
from threading import Event
from unittest.mock import MagicMock, patch

from playwright.sync_api import Error, TimeoutError as PlaywrightTimeout
from quadview.core.link_discovery import LinkFetchError, extract_good_links, get_links


class LinkDiscoveryTests(unittest.TestCase):
    def test_preserves_case_sensitive_filter_and_literal_splitting(self):
        links = [
            "https://site.example/news", "https://site.example/STREAM-one",
            "https://site.example/stream/first-channel",
            "https://site.example/stream/second--channel?tag=a-b#c-d",
            "https://stream.example/", "https://site.example/other?stream=yes",
        ]
        self.assertEqual(extract_good_links(links), {
            "First Channel": links[2],
            "Second  Channel?Tag=A B#C D": links[3],
        })

    def test_requested_match_excludes_league_pages_and_query_fragment_matches(self):
        unwanted = "https://crackstreams.mx/league/nflstreams"
        wanted = "https://crackstreams.mx/stream/buffalo-bills-vs-los-angeles-rams"
        self.assertEqual(extract_good_links([
            unwanted, wanted, "https://site.example/league?next=/stream/game",
            "https://site.example/league#/stream/game", "https://stream.example/news",
            "https://site.example/streams/game", "https://site.example/STREAM/game",
        ]), {"Buffalo Bills Vs Los Angeles Rams": wanted})

    def test_name_collisions_keep_last_url_and_original_name_order(self):
        first = "https://one.example/stream/same-name"
        last = "https://two.example/stream/same-name"
        self.assertEqual(extract_good_links([first, "https://a.example/stream/different", last]), {
            "Same Name": last, "Different": "https://a.example/stream/different",
        })

    def browser_context(self):
        context = MagicMock()
        playwright = context.return_value.__enter__.return_value
        browser = playwright.chromium.launch.return_value
        page = browser.new_page.return_value
        return context, playwright, browser, page

    def test_fetch_uses_visible_browser_load_timeout_and_always_closes(self):
        context, playwright, browser, page = self.browser_context()
        with patch("quadview.core.link_discovery.sync_playwright", context), patch("quadview.core.link_discovery.extract_links", return_value=["https://site.example/stream/stream-one"]):
            self.assertEqual(get_links("page.example"), ["https://site.example/stream/stream-one"])
        playwright.chromium.launch.assert_called_once_with(headless=False, timeout=15_000)
        page.goto.assert_called_once_with("https://page.example", wait_until="load", timeout=60_000)
        browser.close.assert_called_once()

    def test_timeout_redacts_call_log_and_still_closes_browser(self):
        context, _playwright, browser, page = self.browser_context()
        page.goto.side_effect = PlaywrightTimeout("sensitive-url-and-call-log")
        with patch("quadview.core.link_discovery.sync_playwright", context):
            with self.assertRaises(LinkFetchError) as caught:
                get_links("page.example")
        self.assertNotIn("sensitive", str(caught.exception))
        browser.close.assert_called_once()

    def test_missing_browser_actionable_error_and_cancellation_before_launch(self):
        context, playwright, _browser, _page = self.browser_context()
        playwright.chromium.launch.side_effect = Error("Executable doesn't exist")
        with patch("quadview.core.link_discovery.sync_playwright", context):
            with self.assertRaisesRegex(LinkFetchError, "uv run playwright install chromium"):
                get_links("page.example")
        cancel = Event()
        cancel.set()
        with patch("quadview.core.link_discovery.sync_playwright") as start:
            with self.assertRaisesRegex(LinkFetchError, "cancelled"):
                get_links("page.example", cancelled=cancel)
            start.assert_not_called()

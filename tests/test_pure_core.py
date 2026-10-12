"""Tests that run without a browser, GUI, network, or Windows API."""

from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from quadview.core.config_manager import ConfigManager, default_config_path
from quadview.core.layout_manager import quadrants, regions_for_count
from quadview.core.models import AppConfig, DEFAULT_SOURCE_URL, Rect
from quadview.core.url_validation import normalize_url


class UrlValidationTests(unittest.TestCase):
    def test_normalizes_only_missing_scheme(self) -> None:
        cases = {
            "example.com/a?q=hello%20world#section": "https://example.com/a?q=hello%20world#section",
            "example.com:8080/path": "https://example.com:8080/path",
            "localhost:3000": "https://localhost:3000",
            "intranet:8443/path": "https://intranet:8443/path",
            "[2001:db8::1]:8443/video": "https://[2001:db8::1]:8443/video",
            "192.168.1.10:8080": "https://192.168.1.10:8080",
            "//example.com/path": "https://example.com/path",
            "http://example.com/a": "http://example.com/a",
            "HTTPS://Example.COM/A?case=Yes": "HTTPS://Example.COM/A?case=Yes",
            "https://例え.テスト/動画": "https://例え.テスト/動画",
            "https://example.com./": "https://example.com./",
        }
        for candidate, expected in cases.items():
            with self.subTest(candidate=candidate):
                self.assertEqual(normalize_url(candidate), expected)

    def test_rejects_non_web_schemes_credentials_and_bad_authorities(self) -> None:
        cases = (
            "", "ftp://example.com", "file:///C:/secret.txt", "javascript:1",
            "about:123", "data:text/plain,hello", "custom:payload", "http:example.com",
            "https:///example.com", "https://", "https://user:password@example.com",
            "https://@example.com", "https://example.com:0", "example.com:65536",
            "https://example.com:", "https://example.com:abc", "https://-bad.example",
            "https://bad-.example", "https://bad_name.example", "https://a..example",
            "https://example.com..", "https://999.2.3.4", "https://1.2.3",
            "https://[::1]suffix", "https://[not-ip]", "https://2001:db8::1",
            "https://[fe80::1%25zone]", "https://exa%mple.com", "https://a\\b.com",
            " https://example.com", "https://example.com/a b", "https://example.com/\n",
            "https://example.com/\x00", "https://example.com/\u200b",
            "https://" + "a" * 64 + ".example",
        )
        for candidate in cases:
            with self.subTest(candidate=candidate):
                with self.assertRaises(ValueError):
                    normalize_url(candidate)


class LayoutTests(unittest.TestCase):
    def test_all_counts_cover_odd_negative_work_area_without_overlap(self) -> None:
        area = Rect(-1001, -101, 0, 600)
        for count in range(1, 5):
            regions = regions_for_count(area, count)
            self.assertEqual(len(regions), count)
            self.assertEqual(sum(rect.width * rect.height for rect in regions), area.width * area.height)
            for index, first in enumerate(regions):
                for second in regions[index + 1:]:
                    self.assertTrue(first.right <= second.left or second.right <= first.left or first.bottom <= second.top or second.bottom <= first.top)
        self.assertEqual(regions_for_count(area, 1), (area,))
        self.assertEqual(regions_for_count(area, 2), (Rect(-1001, -101, -501, 600), Rect(-501, -101, 0, 600)))
        self.assertEqual(regions_for_count(area, 3), (Rect(-1001, -101, -501, 600), Rect(-501, -101, 0, 249), Rect(-501, 249, 0, 600)))
        self.assertEqual(regions_for_count(area, 4), quadrants(area))

    def test_adaptive_count_validation(self) -> None:
        for count in (0, 5, True, 2.0):
            with self.assertRaises(ValueError):
                regions_for_count(Rect(0, 0, 1920, 1080), count)

    def test_even_work_area(self) -> None:
        self.assertEqual(
            quadrants(Rect(0, 0, 1920, 1040)),
            (Rect(0, 0, 960, 520), Rect(960, 0, 1920, 520),
             Rect(0, 520, 960, 1040), Rect(960, 520, 1920, 1040)),
        )

    def test_odd_signed_geometry_has_complete_nonoverlapping_coverage(self) -> None:
        area = Rect(-1921, -501, 0, 540)
        top_left, top_right, bottom_left, bottom_right = quadrants(area)
        self.assertEqual(top_left, Rect(-1921, -501, -961, 19))
        self.assertEqual(top_right.width, top_left.width + 1)
        self.assertEqual(bottom_left.height, top_left.height + 1)
        self.assertEqual(top_left.right, top_right.left)
        self.assertEqual(bottom_left.right, bottom_right.left)
        self.assertEqual(top_left.bottom, bottom_left.top)
        self.assertEqual(top_right.bottom, bottom_right.top)
        self.assertEqual(bottom_right.right, area.right)
        self.assertEqual(bottom_right.bottom, area.bottom)
        self.assertEqual(sum(rect.width * rect.height for rect in quadrants(area)), area.width * area.height)

    def test_rejects_degenerate_or_noninteger_work_areas(self) -> None:
        for area in (Rect(0, 0, 1, 100), Rect(0, 0, 100, 1), Rect(5, 0, 2, 100), Rect(0, 0, 2.5, 5)):
            with self.subTest(area=area), self.assertRaises(ValueError):
                quadrants(area)


class ConfigTests(unittest.TestCase):
    def test_default_source_and_legacy_fullscreen_setting(self) -> None:
        self.assertEqual(self.manager.load().source_url, "https://crackstreams.mx/league/nflstreams")
        self._write(b'{"version":1,"auto_fullscreen":true,"urls":[]}')
        self.assertFalse(hasattr(self.manager.load(), "auto_fullscreen"))
        self._write(b'{"version":1,"source_url":"","urls":[]}')
        self.assertEqual(self.manager.load().source_url, DEFAULT_SOURCE_URL)

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "settings" / "config.json"
        self.manager = ConfigManager(self.path)

    def _write(self, raw: bytes) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(raw)

    def test_default_location_uses_local_app_data(self) -> None:
        with patch.dict(os.environ, {"LOCALAPPDATA": self.directory.name}):
            self.assertEqual(default_config_path(), Path(self.directory.name) / "QuadView" / "config.json")

    def test_missing_file_returns_independent_defaults_without_creating_files(self) -> None:
        first = self.manager.load()
        first.urls.append("changed")
        self.assertEqual(self.manager.load().urls, [])
        self.assertIsNone(self.manager.last_warning)
        self.assertFalse(self.path.exists())

    def test_round_trip_preserves_signed_geometry_unicode_and_explicit_http(self) -> None:
        config = AppConfig(
            urls=["http://example.com", "https://例え.テスト", "localhost:3000", "https://example.org"],
            executable_path=r"C:\Program Files\LibreWolf\librewolf.exe",
            monitor_id=r"\\.\DISPLAY2",
            monitor_bounds=Rect(-1920, -100, 0, 980),
            window_geometry=Rect(-1800, 20, -1200, 700),
        )
        self.manager.save(config)
        self.assertEqual(self.manager.load(), config)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), asdict(config))
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_invalid_files_are_untouched_until_save_and_backed_up_exactly(self) -> None:
        for original in (
            b"{broken json", b"\xff\xfeinvalid", b'{"version":2,"future":true}',
            b'{"version":0}', b'{"version":true}', b'{"version":1,"urls":["1","2","3","4","5"]}',
            b'{"version":1,"window_geometry":{"left":0,"top":0,"right":-1,"bottom":9}}',
        ):
            with self.subTest(original=original):
                self._write(original)
                self.assertEqual(self.manager.load(), AppConfig())
                self.assertIsNotNone(self.manager.last_warning)
                self.assertEqual(self.path.read_bytes(), original)
                backups_before = set(self.path.parent.glob("*.backup.json"))
                self.manager.save(AppConfig())
                backups = set(self.path.parent.glob("*.backup.json")) - backups_before
                self.assertEqual(len(backups), 1)
                self.assertEqual(backups.pop().read_bytes(), original)
                self.assertEqual(self.manager.load(), AppConfig())

    def test_save_without_load_still_preserves_existing_unknown_version(self) -> None:
        original = b'{"version":999,"unknown":[1,2,3]}'
        self._write(original)
        self.manager.save(AppConfig())
        self.assertEqual(next(self.path.parent.glob("*.backup.json")).read_bytes(), original)

    def test_failed_atomic_replace_preserves_existing_settings_and_removes_temp(self) -> None:
        self.manager.save(AppConfig(urls=["old", "", "", ""]))
        original = self.path.read_bytes()
        with patch("quadview.core.config_manager.os.replace", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                self.manager.save(AppConfig(urls=["new", "", "", ""]))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])

    def test_failure_to_backup_leaves_invalid_original_untouched(self) -> None:
        original = b"{broken"
        self._write(original)
        self.manager.load()
        with patch("quadview.core.config_manager.Path.read_bytes", side_effect=OSError("denied")):
            with self.assertRaises(OSError):
                self.manager.save(AppConfig())
        self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_in_memory_config_is_not_saved(self) -> None:
        with self.assertRaises(ValueError):
            self.manager.save(AppConfig(urls=["one"] * 5))
        self.assertFalse(self.path.exists())

    def test_source_and_variable_selection_round_trip_and_old_config_compatibility(self) -> None:
        for count in range(5):
            config = AppConfig(source_url="https://page.example/streams", urls=[f"https://stream.example/{index}" for index in range(count)])
            self.manager.save(config)
            self.assertEqual(self.manager.load(), config)
        self._write(b'{"version":1,"urls":["old.example","","",""]}')
        self.assertEqual(self.manager.load().source_url, DEFAULT_SOURCE_URL)
        self.assertEqual(self.manager.load().urls[0], "old.example")


if __name__ == "__main__":
    unittest.main()

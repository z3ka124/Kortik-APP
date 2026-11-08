# -*- coding: utf-8 -*-
"""Testovi za preuzimanje instalera — bez mreze (validacije pre download-a)."""
import asyncio
import sys
import tempfile
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.updater.installer import (  # noqa: E402
    MAX_INSTALLER_BYTES,
    UpdateError,
    _validate_manifest,
    download_installer,
    launch_installer,
    verify_authenticode,
)

GOOD_SHA = "a" * 64


class ManifestValidationTests(unittest.TestCase):
    def test_https_is_required(self):
        with self.assertRaises(UpdateError):
            _validate_manifest({"url": "http://cdn/x.exe", "sha256": GOOD_SHA, "size": 5000})

    def test_missing_sha256(self):
        with self.assertRaises(UpdateError):
            _validate_manifest({"url": "https://cdn/x.exe", "size": 5000})

    def test_absurd_size(self):
        with self.assertRaises(UpdateError):
            _validate_manifest(
                {"url": "https://cdn/x.exe", "sha256": GOOD_SHA, "size": MAX_INSTALLER_BYTES + 1}
            )

    def test_valid_manifest_passes(self):
        _validate_manifest({"url": "https://cdn/x.exe", "sha256": GOOD_SHA, "size": 5_000_000})


class DownloadGuardsTests(unittest.TestCase):
    def test_download_rejects_http_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(UpdateError):
                asyncio.run(
                    download_installer(
                        {"url": "http://insecure/x.exe", "sha256": GOOD_SHA, "size": 5000},
                        Path(tmp),
                    )
                )

    def test_download_rejects_missing_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(UpdateError):
                asyncio.run(
                    download_installer(
                        {"url": "https://cdn/x.exe", "size": 5000},
                        Path(tmp),
                    )
                )


class InstallerHelpersTests(unittest.TestCase):
    def test_launch_missing_file(self):
        with self.assertRaises(UpdateError):
            launch_installer(Path("ne-postoji-installer.exe"))

    def test_authenticode_missing_file(self):
        ok, reason = verify_authenticode(Path("ne-postoji.exe"))
        self.assertFalse(ok)
        self.assertIn(reason, ("file_missing", "not_windows"))


if __name__ == "__main__":
    unittest.main()

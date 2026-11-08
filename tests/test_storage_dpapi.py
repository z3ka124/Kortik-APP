# -*- coding: utf-8 -*-
"""Testovi za DPAPI i lokalno cuvanje tajni."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.security import dpapi  # noqa: E402
from app.security.storage import (  # noqa: E402
    ALLOW_INSECURE_ENV,
    SecretStore,
    SecretStoreError,
)


@unittest.skipUnless(dpapi.is_available(), "DPAPI postoji samo na Windows-u")
class DpapiTests(unittest.TestCase):
    def test_roundtrip(self):
        secret = b'{"device_secret":"tajna-vrednost"}'
        blob = dpapi.protect(secret)
        self.assertNotEqual(blob, secret)
        self.assertNotIn(b"tajna-vrednost", blob)
        self.assertEqual(dpapi.unprotect(blob), secret)

    def test_entropy_mismatch_fails(self):
        blob = dpapi.protect(b"podaci", entropy=b"entropy-A")
        with self.assertRaises(OSError):
            dpapi.unprotect(blob, entropy=b"entropy-B")

    def test_empty_input_rejected(self):
        with self.assertRaises(ValueError):
            dpapi.protect(b"")
        with self.assertRaises(ValueError):
            dpapi.unprotect(b"")

    def test_garbage_input_rejected(self):
        with self.assertRaises(OSError):
            dpapi.unprotect(b"ovo-nije-dpapi-blob")


class SecretStoreTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "secrets.bin"

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_and_load_roundtrip(self):
        if not SecretStore(self.path).is_available():
            self.skipTest("ni DPAPI ni insecure rezim nisu dostupni")
        store = SecretStore(self.path)
        payload = {"device_id": "abc", "device_secret": "s3cr3t-value", "refresh_token": "r3fr3sh"}
        store.save(payload)
        self.assertTrue(self.path.exists())
        self.assertEqual(store.load(), payload)

    def test_missing_file_returns_none(self):
        self.assertIsNone(SecretStore(self.path).load())

    def test_corrupted_file_returns_none(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_bytes(b"ovo-nije-nas-format")
        self.assertIsNone(SecretStore(self.path).load())

    def test_insecure_fallback_requires_opt_in(self):
        with mock.patch.dict(os.environ, {ALLOW_INSECURE_ENV: "1"}):
            with mock.patch("app.security.dpapi.is_available", return_value=False):
                store = SecretStore(self.path)
                self.assertTrue(store.is_available())
                store.save({"device_secret": "x"})
                self.assertEqual(store.load(), {"device_secret": "x"})
                self.assertTrue(self.path.read_bytes().startswith(b"INSECURE1\n"))

    def test_refuses_to_save_without_dpapi(self):
        with mock.patch.dict(os.environ, {ALLOW_INSECURE_ENV: "0"}):
            with mock.patch("app.security.dpapi.is_available", return_value=False):
                store = SecretStore(self.path)
                with self.assertRaises(SecretStoreError):
                    store.save({"device_secret": "x"})
                self.assertFalse(self.path.exists())

    def test_empty_payload_rejected(self):
        store = SecretStore(self.path)
        with self.assertRaises(SecretStoreError):
            store.save({})

    def test_clear(self):
        if not SecretStore(self.path).is_available():
            self.skipTest("storage nije dostupan")
        store = SecretStore(self.path)
        store.save({"a": "b"})
        store.clear()
        self.assertIsNone(store.load())
        store.clear()  # idempotentno


if __name__ == "__main__":
    unittest.main()

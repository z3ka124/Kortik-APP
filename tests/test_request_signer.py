# -*- coding: utf-8 -*-
"""
Testovi za HMAC potpisivanje u aplikaciji + CROSS-CHECK sa backendom.

Pokretanje (iz Kortik-Listener-App):
    python -m unittest discover -s tests -p "test_*.py" -v
"""
import importlib.util
import sys
import time
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = APP_ROOT.parent
BACKEND_MODULE = (
    REPO_ROOT / "Kortik-Bot Dashabord" / "Kortik-Dahabord-Backend" / "listener_security.py"
)
BOT_MODULE = REPO_ROOT / "Kortik-Bot" / "services" / "security" / "internal_auth.py"

if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.security.request_signer import (  # noqa: E402
    SIGNATURE_HEADER,
    NONCE_HEADER,
    TIMESTAMP_HEADER,
    canonical_request,
    new_nonce,
    sign_request,
    signed_headers,
    verify_request_signature,
)

SECRET = "device-secret-0123456789abcdef"
PATH = "/api/listener/command"
BODY = b'{"command":"play","query":"senidah","request_id":"abc-12345678"}'
NONCE = "a1b2c3d4e5f60718"


def _load(path: Path, name: str):
    if not path.exists():
        return None
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RequestSignerTests(unittest.TestCase):
    def test_sign_and_verify_roundtrip(self):
        ts = int(time.time())
        signature = sign_request(SECRET, "POST", PATH, ts, NONCE, BODY)
        ok, reason = verify_request_signature(
            secret=SECRET, method="POST", path=PATH, timestamp=ts,
            nonce=NONCE, body=BODY, signature=signature,
        )
        self.assertTrue(ok, reason)

    def test_tampered_body_is_rejected(self):
        ts = int(time.time())
        signature = sign_request(SECRET, "POST", PATH, ts, NONCE, BODY)
        ok, reason = verify_request_signature(
            secret=SECRET, method="POST", path=PATH, timestamp=ts,
            nonce=NONCE, body=BODY + b"x", signature=signature,
        )
        self.assertEqual((ok, reason), (False, "bad_signature"))

    def test_skew_is_rejected(self):
        ts = int(time.time()) - 600
        signature = sign_request(SECRET, "POST", PATH, ts, NONCE, BODY)
        ok, reason = verify_request_signature(
            secret=SECRET, method="POST", path=PATH, timestamp=ts,
            nonce=NONCE, body=BODY, signature=signature,
        )
        self.assertEqual((ok, reason), (False, "clock_skew"))

    def test_signed_headers_shape(self):
        headers = signed_headers(SECRET, "POST", PATH, BODY)
        self.assertIn(TIMESTAMP_HEADER, headers)
        self.assertIn(NONCE_HEADER, headers)
        self.assertIn(SIGNATURE_HEADER, headers)
        self.assertEqual(len(headers[NONCE_HEADER]), 32)
        self.assertEqual(len(headers[SIGNATURE_HEADER]), 64)

        ok, reason = verify_request_signature(
            secret=SECRET,
            method="POST",
            path=PATH,
            timestamp=headers[TIMESTAMP_HEADER],
            nonce=headers[NONCE_HEADER],
            body=BODY,
            signature=headers[SIGNATURE_HEADER],
        )
        self.assertTrue(ok, reason)

    def test_nonce_is_random(self):
        self.assertNotEqual(new_nonce(), new_nonce())


class CrossImplementationTests(unittest.TestCase):
    """Aplikacija i backend MORAJU potpisivati identicno."""

    def test_canonical_matches_backend(self):
        backend = _load(BACKEND_MODULE, "backend_listener_security")
        if backend is None:
            self.skipTest("backend modul nije pronadjen")
        ts = 1700000000
        self.assertEqual(
            canonical_request("POST", PATH, ts, NONCE, BODY),
            backend.canonical_request("POST", PATH, ts, NONCE, BODY),
        )

    def test_signature_matches_backend(self):
        backend = _load(BACKEND_MODULE, "backend_listener_security")
        if backend is None:
            self.skipTest("backend modul nije pronadjen")
        ts = 1700000000
        self.assertEqual(
            sign_request(SECRET, "POST", PATH, ts, NONCE, BODY),
            backend.sign_request(SECRET, "POST", PATH, ts, NONCE, BODY),
        )

    def test_backend_accepts_app_signature(self):
        backend = _load(BACKEND_MODULE, "backend_listener_security")
        if backend is None:
            self.skipTest("backend modul nije pronadjen")
        now = time.time()
        ts = int(now)
        headers = signed_headers(SECRET, "POST", PATH, BODY, timestamp=ts)
        ok, reason = backend.verify_request_signature(
            secret=SECRET, method="POST", path=PATH, timestamp=headers[TIMESTAMP_HEADER],
            nonce=headers[NONCE_HEADER], body=BODY, signature=headers[SIGNATURE_HEADER], now=now,
        )
        self.assertTrue(ok, reason)

    def test_signature_matches_bot_module(self):
        bot = _load(BOT_MODULE, "bot_internal_auth")
        if bot is None:
            self.skipTest("bot modul nije pronadjen")
        ts = 1700000000
        self.assertEqual(
            sign_request(SECRET, "POST", PATH, ts, NONCE, BODY),
            bot.sign_request(SECRET, "POST", PATH, ts, NONCE, BODY),
        )


if __name__ == "__main__":
    unittest.main()

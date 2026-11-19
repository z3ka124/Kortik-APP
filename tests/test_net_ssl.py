# -*- coding: utf-8 -*-
"""Testovi za zajednički TLS kontekst (app/net/ssl.py) — bez mreže."""
import ssl
import sys
import unittest
from pathlib import Path
from unittest import mock

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.net.ssl import _load_windows_certs, create_client_ssl_context  # noqa: E402


class CreateClientSslContextTests(unittest.TestCase):
    def test_returns_ssl_context_with_verification_on(self):
        ctx = create_client_ssl_context()
        self.assertIsInstance(ctx, ssl.SSLContext)
        self.assertEqual(ctx.verify_mode, ssl.CERT_REQUIRED)

    def test_does_not_raise_when_certifi_is_missing(self):
        with mock.patch("app.net.ssl.certifi", None):
            ctx = create_client_ssl_context()
            self.assertIsInstance(ctx, ssl.SSLContext)


class LoadWindowsCertsTests(unittest.TestCase):
    @staticmethod
    def _bare_context() -> ssl.SSLContext:
        return ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)

    def test_invalid_cert_is_skipped(self):
        """Jedan neispravan unos u cert store-u ne sme da prekine učitavanje."""
        ctx = self._bare_context()
        good_pem = (
            "-----BEGIN CERTIFICATE-----\n"
            "QUJDRA==\n"
            "-----END CERTIFICATE-----\n"
        )

        def fake_enum(store_name):  # noqa: ARG001 — potpis enum_certificates
            return [(b"bad-cert", "DER", True), (b"good-cert", "DER", True)]

        def fake_der_to_pem(der_bytes):
            if der_bytes == b"bad-cert":
                raise ValueError("loš cert")
            return good_pem

        with mock.patch.object(ssl, "enum_certificates", fake_enum, create=True), \
             mock.patch.object(ssl, "DER_cert_to_PEM_cert", side_effect=fake_der_to_pem, create=True), \
             mock.patch.object(ctx, "load_verify_locations") as load_mock:
            _load_windows_certs(ctx)

            self.assertTrue(load_mock.called)
            self.assertIn(good_pem, load_mock.call_args.kwargs["cadata"])
            self.assertNotIn("bad-cert", load_mock.call_args.kwargs["cadata"])

    def test_enum_certificates_raising_is_safe(self):
        def raising_enum(store_name):  # noqa: ARG001 — potpis enum_certificates
            raise RuntimeError("store nedostupan")

        ctx = self._bare_context()
        with mock.patch.object(ssl, "enum_certificates", raising_enum, create=True):
            _load_windows_certs(ctx)  # ne sme da digne izuzetak


if __name__ == "__main__":
    unittest.main()
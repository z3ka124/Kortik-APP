# -*- coding: utf-8 -*-
"""Testovi za verifikaciju update manifesta (Ed25519 + SHA-256)."""
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.updater import manifest as mf  # noqa: E402

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover
    CRYPTO_AVAILABLE = False


@unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography nije instaliran")
class ManifestValidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.private_key = Ed25519PrivateKey.generate()
        cls.public_hex = cls.private_key.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw
        ).hex()

    def _manifest(self, **overrides):
        payload = {
            "version": "1.2.0",
            "min_version": "0.1.0",
            "url": "https://cdn.kortikbot.xyz/listener/setup-1.2.0.exe",
            "sha256": "a" * 64,
            "size": 12345,
            "notes": "test",
            "channel": "stable",
        }
        payload.update(overrides)
        signature = self.private_key.sign(mf.canonical_manifest(payload)).hex()
        return {**payload, "sig": signature}

    def test_valid_manifest_passes(self):
        ok, reason = mf.validate_manifest(self._manifest(), "1.0.0", self.public_hex)
        self.assertTrue(ok, reason)

    def test_tampered_version_fails(self):
        manifest = self._manifest()
        manifest["version"] = "1.3.0"
        ok, reason = mf.validate_manifest(manifest, "1.0.0", self.public_hex)
        self.assertFalse(ok)
        self.assertEqual(reason, "bad_signature")

    def test_http_url_is_rejected(self):
        manifest = self._manifest(url="http://cdn.kortikbot.xyz/setup.exe")
        ok, reason = mf.validate_manifest(manifest, "1.0.0", self.public_hex)
        self.assertEqual((ok, reason), (False, "insecure_url"))

    def test_downgrade_is_blocked(self):
        manifest = self._manifest(version="0.9.0", min_version="0.1.0")
        ok, reason = mf.validate_manifest(manifest, "1.0.0", self.public_hex)
        self.assertEqual((ok, reason), (False, "downgrade_blocked"))

    def test_min_version_forces_update(self):
        manifest = self._manifest(version="1.2.0", min_version="1.5.0")
        ok, reason = mf.validate_manifest(manifest, "1.0.0", self.public_hex)
        self.assertEqual((ok, reason), (False, "update_required"))

    def test_bad_sha_format(self):
        manifest = self._manifest(sha256="xyz")
        ok, reason = mf.validate_manifest(manifest, "1.0.0", self.public_hex)
        self.assertEqual((ok, reason), (False, "bad_sha256"))

    def test_missing_signature(self):
        manifest = self._manifest()
        manifest.pop("sig")
        ok, reason = mf.validate_manifest(manifest, "1.0.0", self.public_hex)
        self.assertEqual((ok, reason), (False, "missing_signature"))

    def test_missing_public_key(self):
        ok, reason = mf.validate_manifest(self._manifest(), "1.0.0", "")
        self.assertEqual((ok, reason), (False, "missing_public_key"))

    def test_wrong_public_key(self):
        other = Ed25519PrivateKey.generate().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
        ok, reason = mf.validate_manifest(self._manifest(), "1.0.0", other)
        self.assertEqual((ok, reason), (False, "bad_signature"))

    def test_incomplete_manifest(self):
        manifest = self._manifest()
        manifest.pop("url")
        ok, reason = mf.validate_manifest(manifest, "1.0.0", self.public_hex)
        self.assertEqual((ok, reason), (False, "missing_url"))


class VersionTests(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(mf.parse_version("1.2.3"), (1, 2, 3, 0))
        self.assertEqual(mf.parse_version("v2.0"), (2, 0, 0, 0))
        self.assertEqual(mf.parse_version("nije-verzija"), ())

    def test_is_newer(self):
        self.assertTrue(mf.is_newer("1.2.0", "1.1.9"))
        self.assertFalse(mf.is_newer("1.0.0", "1.0.0"))
        self.assertFalse(mf.is_newer("0.9.0", "1.0.0"))
        self.assertFalse(mf.is_newer("garbage", "1.0.0"))

    def test_is_downgrade_for_invalid_input_is_safe(self):
        self.assertTrue(mf.is_downgrade("garbage", "1.0.0"))
        self.assertTrue(mf.is_downgrade("1.0.0", "garbage"))

    def test_needs_update(self):
        self.assertTrue(mf.needs_update({"version": "2.0.0"}, "1.9.9"))
        self.assertFalse(mf.needs_update({"version": "1.0.0"}, "1.0.0"))
        self.assertFalse(mf.needs_update({}, "1.0.0"))


class FileHashTests(unittest.TestCase):
    def test_sha256_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "installer.exe"
            payload = b"kortik-installer-bytes"
            path.write_bytes(payload)
            expected = hashlib.sha256(payload).hexdigest()

            ok, reason = mf.verify_file_sha256(path, expected)
            self.assertTrue(ok, reason)
            self.assertEqual(mf.file_sha256(path), expected)

    def test_sha256_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "installer.exe"
            path.write_bytes(b"drugi sadrzaj")
            ok, reason = mf.verify_file_sha256(path, "b" * 64)
            self.assertEqual((ok, reason), (False, "sha256_mismatch"))

    def test_missing_file(self):
        ok, reason = mf.verify_file_sha256(Path("ne-postoji.exe"), "a" * 64)
        self.assertEqual((ok, reason), (False, "file_missing"))


if __name__ == "__main__":
    unittest.main()

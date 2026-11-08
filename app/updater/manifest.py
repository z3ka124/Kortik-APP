# c:\Kortik\Kortik-Listener-App\app\updater\manifest.py
"""
Verifikacija update manifesta.

Pravila (sve fail-closed):
  1. Manifest mora imati `version`, `url`, `sha256`, `sig`.
  2. `url` mora biti HTTPS — nikad ne skidamo installer preko HTTP-a.
  3. Ed25519 potpis se proverava nad kanonizovanim JSON-om (bez `sig` polja)
     javnim kljucem ugradjenim u aplikaciju.
  4. `version` mora biti veca od trenutne; `min_version` blokira preskakanje.
  5. Tek posle toga se proverava SHA-256 skinutog fajla.

Kanonizacija je identicna kao u backendu (`listener_security.canonical_manifest`).
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Tuple

PUBKEY_HEX_LEN = 64
SIG_HEX_LEN = 128

_VERSION_RE = re.compile(r"^\d+(\.\d+){1,3}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def canonical_manifest(manifest: Dict[str, Any]) -> bytes:
    payload = {k: v for k, v in (manifest or {}).items() if k != "sig"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def parse_version(value: str) -> Tuple[int, ...]:
    text = str(value or "").strip().lstrip("vV")
    if not _VERSION_RE.match(text):
        return ()
    parts = [int(p) for p in text.split(".")]
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)


def is_newer(remote: str, local: str) -> bool:
    remote_parts = parse_version(remote)
    local_parts = parse_version(local)
    if not remote_parts or not local_parts:
        return False
    return remote_parts > local_parts


def is_downgrade(remote: str, local: str) -> bool:
    remote_parts = parse_version(remote)
    local_parts = parse_version(local)
    if not remote_parts or not local_parts:
        return True
    return remote_parts < local_parts


def verify_signature(manifest: Dict[str, Any], public_key_hex: str) -> Tuple[bool, str]:
    """Proverava Ed25519 potpis manifesta."""
    if not public_key_hex:
        return False, "missing_public_key"
    if len(str(public_key_hex).strip()) != PUBKEY_HEX_LEN:
        return False, "bad_public_key"

    signature = str((manifest or {}).get("sig") or "").strip().lower()
    if not signature:
        return False, "missing_signature"
    if len(signature) != SIG_HEX_LEN:
        return False, "bad_signature"

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError:
        return False, "cryptography_missing"

    try:
        key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex.strip()))
        key.verify(bytes.fromhex(signature), canonical_manifest(manifest))
        return True, "ok"
    except InvalidSignature:
        return False, "bad_signature"
    except Exception:
        return False, "bad_signature"


def validate_manifest(
    manifest: Dict[str, Any],
    current_version: str,
    public_key_hex: str,
) -> Tuple[bool, str]:
    """Kompletna provera pre nego sto se bilo sta skine."""
    if not isinstance(manifest, dict):
        return False, "invalid_manifest"

    for field in ("version", "url", "sha256"):
        if not str(manifest.get(field) or "").strip():
            return False, f"missing_{field}"

    version = str(manifest["version"]).strip()
    if not parse_version(version):
        return False, "bad_version"

    url = str(manifest["url"]).strip()
    if not url.lower().startswith("https://"):
        return False, "insecure_url"

    if not _SHA256_RE.match(str(manifest["sha256"]).strip().lower()):
        return False, "bad_sha256"

    if is_downgrade(version, current_version):
        return False, "downgrade_blocked"

    min_version = str(manifest.get("min_version") or "").strip()
    if min_version and parse_version(min_version):
        if is_downgrade(current_version, min_version):
            return False, "update_required"

    ok, reason = verify_signature(manifest, public_key_hex)
    if not ok:
        return False, reason

    return True, "ok"


def file_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file_sha256(path: Path, expected: str) -> Tuple[bool, str]:
    path = Path(path)
    if not path.exists():
        return False, "file_missing"
    expected = str(expected or "").strip().lower()
    if not _SHA256_RE.match(expected):
        return False, "bad_sha256"
    actual = file_sha256(path)
    if actual != expected:
        return False, "sha256_mismatch"
    return True, "ok"


def needs_update(manifest: Dict[str, Any], current_version: str) -> bool:
    return is_newer(str((manifest or {}).get("version") or ""), current_version)

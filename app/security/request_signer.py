# c:\Kortik\Kortik-Listener-App\app\security\request_signer.py
"""
HMAC potpisivanje zahteva ka Kortik backend-u.

MORA biti bit-identicno sa:
  * Kortik-Bot Dashabord/.../listener_security.py   (backend, verifikuje)
  * Kortik-Bot/services/security/internal_auth.py   (bot, verifikuje interno)

Format:
    HMAC_SHA256(secret, METHOD \\n PATH \\n TIMESTAMP \\n NONCE \\n SHA256(BODY))

`tests/test_request_signer.py` radi cross-check sa backend modulom, pa se
divergencija ne moze desiti tiho.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Dict, Optional, Tuple

SIGNATURE_HEADER = "X-Kortik-Signature"
NONCE_HEADER = "X-Kortik-Nonce"
TIMESTAMP_HEADER = "X-Kortik-Ts"

MAX_CLOCK_SKEW_SECONDS = 60
NONCE_BYTES = 16


def body_digest(body: bytes | str | None) -> str:
    if body is None:
        payload = b""
    elif isinstance(body, str):
        payload = body.encode("utf-8")
    else:
        payload = bytes(body)
    return hashlib.sha256(payload).hexdigest()


def canonical_request(
    method: str,
    path: str,
    timestamp: int | str,
    nonce: str,
    body: bytes | str | None,
) -> bytes:
    return "\n".join(
        [
            (method or "").upper(),
            path or "",
            str(timestamp),
            nonce or "",
            body_digest(body),
        ]
    ).encode("utf-8")


def sign_request(
    secret: str,
    method: str,
    path: str,
    timestamp: int | str,
    nonce: str,
    body: bytes | str | None = None,
) -> str:
    return hmac.new(
        (secret or "").encode("utf-8"),
        canonical_request(method, path, timestamp, nonce, body),
        hashlib.sha256,
    ).hexdigest()


def new_nonce() -> str:
    return secrets.token_hex(NONCE_BYTES)


def signed_headers(
    secret: str,
    method: str,
    path: str,
    body: bytes | str | None = None,
    timestamp: Optional[int] = None,
) -> Dict[str, str]:
    """Vraca zaglavlja koja se salju uz zahtev (bez Authorization)."""
    ts = int(timestamp if timestamp is not None else time.time())
    nonce = new_nonce()
    return {
        TIMESTAMP_HEADER: str(ts),
        NONCE_HEADER: nonce,
        SIGNATURE_HEADER: sign_request(secret, method, path, ts, nonce, body),
    }


def verify_request_signature(
    *,
    secret: str,
    method: str,
    path: str,
    timestamp: int | str,
    nonce: str,
    body: bytes | str | None,
    signature: str,
    now: Optional[float] = None,
    max_skew: int = MAX_CLOCK_SKEW_SECONDS,
) -> Tuple[bool, str]:
    """Klijentska strana iste provere — koristi se u self-testu i dijagnostici."""
    if not secret:
        return False, "server_secret_missing"
    if not signature:
        return False, "missing_signature"
    if not nonce or len(nonce) < 16:
        return False, "bad_nonce"

    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False, "bad_timestamp"

    current = time.time() if now is None else float(now)
    if abs(current - ts) > max_skew:
        return False, "clock_skew"

    expected = sign_request(secret, method, path, ts, nonce, body)
    if not hmac.compare_digest(expected, str(signature).strip().lower()):
        return False, "bad_signature"
    return True, "ok"

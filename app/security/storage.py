# c:\Kortik\Kortik-Listener-App\app\security\storage.py
"""
Lokalno cuvanje tajni (device secret, refresh token) uz DPAPI.

Format fajla:
    DPAPI1\\n<base64(DPAPI blob)>      -> normalan, bezbedan nacin
    INSECURE1\\n<base64(json)>         -> SAMO za razvoj/test (env override)

Ako DPAPI nije dostupan i nema eksplicitnog override-a, `save()` baca gresku —
nikad ne upisujemo tajne u plaintext "da bi proradilo".
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from app.security import dpapi

ALLOW_INSECURE_ENV = "KORTIK_ALLOW_INSECURE_STORAGE"
_DPAPI_PREFIX = b"DPAPI1\n"
_INSECURE_PREFIX = b"INSECURE1\n"


class SecretStoreError(RuntimeError):
    pass


class SecretStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    @staticmethod
    def insecure_allowed() -> bool:
        return os.getenv(ALLOW_INSECURE_ENV, "").strip() == "1"

    def is_available(self) -> bool:
        return dpapi.is_available() or self.insecure_allowed()

    def save(self, payload: Dict[str, Any]) -> None:
        if not isinstance(payload, dict) or not payload:
            raise SecretStoreError("Nema sta da se sacuva.")

        raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

        if dpapi.is_available():
            data = _DPAPI_PREFIX + base64.b64encode(dpapi.protect(raw))
        elif self.insecure_allowed():
            data = _INSECURE_PREFIX + base64.b64encode(raw)
        else:
            raise SecretStoreError(
                "DPAPI nije dostupan. Postavi KORTIK_ALLOW_INSECURE_STORAGE=1 samo za razvoj."
            )

        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_bytes(data)
        try:
            os.chmod(tmp, 0o600)
        except Exception:
            pass
        tmp.replace(self.path)

    def load(self) -> Optional[Dict[str, Any]]:
        if not self.path.exists():
            return None

        data = self.path.read_bytes()
        try:
            if data.startswith(_DPAPI_PREFIX):
                raw = dpapi.unprotect(base64.b64decode(data[len(_DPAPI_PREFIX):]))
            elif data.startswith(_INSECURE_PREFIX):
                raw = base64.b64decode(data[len(_INSECURE_PREFIX):])
            else:
                # Nepoznat/ostecen format — tretiramo kao "nema tajni" (fail closed)
                return None
            payload = json.loads(raw.decode("utf-8"))
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

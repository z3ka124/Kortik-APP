# c:\Kortik\Kortik-Listener-App\app\security\dpapi.py
"""
Windows DPAPI zastita lokalnih tajni (bez pywin32 zavisnosti).

Tajne (device secret, refresh token) se nikad ne cuvaju u plaintextu:
CryptProtectData ih veze za Windows nalog + masinu, pa kopiranje fajla na
drugi racunar ne otkriva nista.

Napomena: na ne-Windows platformama (CI, dev) funkcije bacaju OSError, a
SecretStore tada trazi eksplicitni `allow_insecure=True` preko env varijable.
"""
from __future__ import annotations

import ctypes
import sys
from typing import Optional, Tuple

DEFAULT_ENTROPY = b"KortikListener.v1"

_IS_WINDOWS = sys.platform.startswith("win")

if _IS_WINDOWS:  # pragma: no cover - platformski kod
    from ctypes import wintypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [
            ("cbData", wintypes.DWORD),
            ("pbData", ctypes.POINTER(ctypes.c_char)),
        ]

    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        wintypes.LPCWSTR,
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    _crypt32.CryptProtectData.restype = wintypes.BOOL

    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.POINTER(wintypes.LPWSTR),
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL

    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def is_available() -> bool:
    return _IS_WINDOWS


def _to_blob(data: bytes) -> Tuple["DATA_BLOB", "ctypes.Array"]:
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
    return blob, buffer


def _read_blob(blob: "DATA_BLOB") -> bytes:
    try:
        return ctypes.string_at(blob.pbData, blob.cbData)
    finally:
        _kernel32.LocalFree(ctypes.cast(blob.pbData, ctypes.c_void_p))


def protect(data: bytes, entropy: bytes = DEFAULT_ENTROPY) -> bytes:
    """Sifruje podatke za trenutnog Windows korisnika (user+machine scope)."""
    if not _IS_WINDOWS:
        raise OSError("DPAPI je dostupan samo na Windows-u.")
    if not data:
        raise ValueError("Nema podataka za zastitu.")

    in_blob, in_buf = _to_blob(data)
    ent_blob, ent_buf = _to_blob(entropy) if entropy else (None, None)
    out_blob = DATA_BLOB()

    ok = _crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "Kortik Listener",
        ctypes.byref(ent_blob) if ent_blob else None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError(f"CryptProtectData failed (winerr={ctypes.get_last_error()})")

    _ = (in_buf, ent_buf)  # drzi bafore u zivotu do kraja poziva
    return _read_blob(out_blob)


def unprotect(blob: bytes, entropy: bytes = DEFAULT_ENTROPY) -> bytes:
    """Desifruje podatke koje je protect() napravio na istoj masini/nalogu."""
    if not _IS_WINDOWS:
        raise OSError("DPAPI je dostupan samo na Windows-u.")
    if not blob:
        raise ValueError("Nema podataka za dezasititu.")

    in_blob, in_buf = _to_blob(blob)
    ent_blob, ent_buf = _to_blob(entropy) if entropy else (None, None)
    out_blob = DATA_BLOB()
    description = ctypes.c_wchar_p()

    ok = _crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        ctypes.byref(description),
        ctypes.byref(ent_blob) if ent_blob else None,
        None,
        None,
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise OSError(f"CryptUnprotectData failed (winerr={ctypes.get_last_error()})")

    _ = (in_buf, ent_buf)
    return _read_blob(out_blob)

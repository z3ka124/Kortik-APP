# c:\Kortik\Kortik-Listener-App\app\version.py
"""
Verzija aplikacije i build-time konstante.

UPDATE_PUBLIC_KEY_HEX se popunjava pri buildu (build/sign.ps1 ili CI secret).
Ako je prazan, updater je ONEMOGUCEN (fail closed) — aplikacija radi, ali se
ne moze nadograditi. To je namerno: bolje bez update-a nego bez verifikacije.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "Kortik Listener"
APP_VERSION = os.getenv("KORTIK_LISTENER_VERSION", "1.0.0")
UPDATE_CHANNEL = os.getenv("KORTIK_LISTENER_CHANNEL", "beta")
PLATFORM = "win-x64"

# Produkcijski API. Preko env-a se moze prebaciti na staging.
API_BASE_URL = os.getenv("KORTIK_API_BASE", "https://api.kortikbot.xyz").rstrip("/")


def _bundled_pubkey() -> str:
    """
    Javni Ed25519 kljuc koji build ubaci u `app/update_pubkey.txt`.

    Zasto fajl: u .exe-u nema env varijabli, a updater mora da ima kljuc
    cak i ako korisnik nista ne podesi. `build/build.ps1` upisuje ovaj fajl
    iz `LISTENER_UPDATE_PUBKEY` PRE PyInstaller-a.
    """
    candidates = [Path(__file__).resolve().parent / "update_pubkey.txt"]

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "app" / "update_pubkey.txt")
        candidates.append(Path(meipass) / "update_pubkey.txt")

    for candidate in candidates:
        try:
            value = candidate.read_text(encoding="utf-8").strip()
            if value:
                return value
        except Exception:
            continue
    return ""


# Ed25519 javni kljuc (hex, 64 karaktera). Privatni kljuc NIKAD nije u aplikaciji.
UPDATE_PUBLIC_KEY_HEX = os.getenv("KORTIK_UPDATE_PUBKEY", "").strip() or _bundled_pubkey()

# Minimalna TLS verzija za sve pozive
TLS_MIN_VERSION = "TLSv1_2"

USER_AGENT = f"{APP_NAME}/{APP_VERSION} ({PLATFORM})"

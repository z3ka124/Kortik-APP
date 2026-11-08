# c:\Kortik\Kortik-Listener-App\build\make_manifest.py
"""
Generise POTPISAN update manifest za datu verziju instalera.

Primer (PowerShell):
    $env:LISTENER_UPDATE_SIGNING_KEY = "<64 hex znaka privatnog Ed25519 kljuca>"
    python build/make_manifest.py `
        --installer build/output/installer/KortikListener-0.2.0-setup.exe `
        --version 0.2.0 `
        --url https://cdn.kortikbot.xyz/listener/KortikListener-0.2.0-setup.exe `
        --min-version 0.1.0 `
        --notes "Ispravljen wake word i busy odgovor." `
        --out listener_app_manifest.json

Rezultat se kopira na server pored `main.py` (ili na CDN).
Aplikacija odbija svaki manifest bez validnog potpisa.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parent
BACKEND_DIR = REPO_ROOT / "Kortik-Bot Dashabord" / "Kortik-Dahabord-Backend"

sys.path.insert(0, str(PROJECT_ROOT))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.updater.manifest import canonical_manifest  # noqa: E402


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sign(manifest: dict, key_hex: str) -> str:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private_key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(key_hex.strip()))
    return private_key.sign(canonical_manifest(manifest)).hex()


def build_manifest(
    installer: Path,
    version: str,
    url: str,
    min_version: str,
    notes: str,
    channel: str,
    platform: str,
    published_at: str,
) -> dict:
    if not installer.exists():
        raise SystemExit(f"Installer ne postoji: {installer}")
    if not url.lower().startswith("https://"):
        raise SystemExit("URL mora biti HTTPS (aplikacija odbija HTTP).")

    return {
        "version": version,
        "min_version": min_version,
        "channel": channel,
        "platform": platform,
        "url": url,
        "sha256": file_sha256(installer),
        "size": installer.stat().st_size,
        "notes": notes,
        "published_at": published_at,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Potpisani Kortik Listener update manifest")
    parser.add_argument("--installer", required=True, type=Path)
    parser.add_argument("--version", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--min-version", default="0.1.0")
    parser.add_argument("--notes", default="")
    parser.add_argument("--channel", default="stable")
    parser.add_argument("--platform", default="win-x64")
    parser.add_argument("--out", default="listener_app_manifest.json", type=Path)
    parser.add_argument(
        "--published-at",
        default=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    args = parser.parse_args()

    key_hex = os.getenv("LISTENER_UPDATE_SIGNING_KEY", "").strip()
    if len(key_hex) < 64:
        raise SystemExit(
            "LISTENER_UPDATE_SIGNING_KEY nije postavljen (64 hex znaka). "
            "Bez potpisa aplikacija odbija manifest."
        )

    manifest = build_manifest(
        args.installer,
        args.version,
        args.url,
        args.min_version,
        args.notes,
        args.channel,
        args.platform,
        args.published_at,
    )
    manifest["sig"] = sign(manifest, key_hex)

    out = args.out if args.out.is_absolute() else PROJECT_ROOT / args.out
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"OK  {out}")
    print(f"    version={manifest['version']}  size={manifest['size']}  sha256={manifest['sha256'][:16]}…")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

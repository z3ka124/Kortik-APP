# c:\Kortik\Kortik-Listener-App\app\updater\installer.py
"""
Preuzimanje, verifikacija i pokretanje instalera ažuriranja.

Redosled provere (svaki korak može da prekine update):
  1. URL mora biti HTTPS
  2. `size` iz manifesta mora biti u razumnim granicama
  3. download u `%LOCALAPPDATA%\\Kortik\\Listener\\updates\\`
  4. SHA-256 mora da se poklopi sa potpisanim manifestom
  5. Authenticode potpis mora biti `Valid` (Windows)
  6. tek onda se pokreće installer (`/SILENT /NORESTART`)

Manifest se verifikuje PRE ovoga (`app/updater/manifest.py`).
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Tuple

from app.updater.manifest import verify_file_sha256

logger = logging.getLogger("kortik.listener.updater")

MAX_INSTALLER_BYTES = 512 * 1024 * 1024
MIN_INSTALLER_BYTES = 1024
CHUNK = 1024 * 256


class UpdateError(RuntimeError):
    pass


def _validate_manifest(manifest: Dict[str, Any]) -> None:
    url = str((manifest or {}).get("url") or "")
    if not url.lower().startswith("https://"):
        raise UpdateError("Update URL mora biti HTTPS.")

    try:
        size = int((manifest or {}).get("size") or 0)
    except (TypeError, ValueError):
        size = 0
    if size and not (MIN_INSTALLER_BYTES <= size <= MAX_INSTALLER_BYTES):
        raise UpdateError(f"Installer ima nerealnu veličinu: {size} bajtova.")

    if not str((manifest or {}).get("sha256") or "").strip():
        raise UpdateError("Manifest nema sha256.")


async def download_installer(manifest: Dict[str, Any], dest_dir: Path, timeout_seconds: int = 900) -> Path:
    import aiohttp

    _validate_manifest(manifest)
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    url = str(manifest["url"])
    filename = url.split("/")[-1].split("?")[0] or "KortikListener-setup.exe"
    target = dest_dir / filename
    partial = target.with_suffix(target.suffix + ".part")

    logger.info("Preuzimam ažuriranje: %s", url)
    timeout = aiohttp.ClientTimeout(total=timeout_seconds, connect=15)
    written = 0

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise UpdateError(f"Download nije uspeo (HTTP {response.status}).")

                with open(partial, "wb") as handle:
                    async for chunk in response.content.iter_chunked(CHUNK):
                        written += len(chunk)
                        if written > MAX_INSTALLER_BYTES:
                            raise UpdateError("Installer je veći od dozvoljenog limita.")
                        handle.write(chunk)
    except UpdateError:
        partial.unlink(missing_ok=True)
        raise
    except Exception as e:
        partial.unlink(missing_ok=True)
        raise UpdateError(f"Download greška: {e}") from e

    ok, reason = verify_file_sha256(partial, str(manifest["sha256"]))
    if not ok:
        partial.unlink(missing_ok=True)
        raise UpdateError(f"Integritet fajla nije potvrđen ({reason}).")

    partial.replace(target)
    logger.info("Installer preuzet i verifikovan: %s", target.name)
    return target


def verify_authenticode(path: Path) -> Tuple[bool, str]:
    """Provera Authenticode potpisa preko PowerShell-a (bez eksternih zavisnosti)."""
    if not sys.platform.startswith("win"):
        return False, "not_windows"

    path = Path(path)
    if not path.exists():
        return False, "file_missing"

    escaped = str(path).replace("'", "''")
    script = f"(Get-AuthenticodeSignature -LiteralPath '{escaped}').Status"
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as e:
        return False, f"powershell_error:{e}"

    status = (result.stdout or "").strip()
    if status.lower() == "valid":
        return True, "valid"
    return False, status or "unknown"


def launch_installer(path: Path, silent: bool = True) -> None:
    """Pokreće Inno Setup installer i zatvara aplikaciju (poziva se poslednja)."""
    path = Path(path)
    if not path.exists():
        raise UpdateError("Installer fajl ne postoji.")

    args = [str(path), "/NORESTART"]
    if silent:
        args.insert(1, "/SILENT")

    logger.info("Pokrećem installer: %s", " ".join(args))
    subprocess.Popen(args, close_fds=True)

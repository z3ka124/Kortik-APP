# c:\Kortik\Kortik-Listener-App\build\keygen.py
"""
Generise Ed25519 par kljuceva za potpisivanje update manifesta.

    python build/keygen.py

Ispisuje:
  * PUBLIC  -> ide u aplikaciju (env LISTENER_UPDATE_PUBKEY pri buildu ILI u backend .env)
  * PRIVATE -> SAMO na server/CI (env LISTENER_UPDATE_SIGNING_KEY)

Privatni kljuc NIKAD ne sme u git, u .exe ni na korisnicki racunar.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import (
        Encoding,
        NoEncryption,
        PrivateFormat,
        PublicFormat,
    )
except ImportError:
    raise SystemExit("Nedostaje 'cryptography': pip install cryptography")


def main() -> int:
    private_key = Ed25519PrivateKey.generate()
    private_hex = private_key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption()).hex()
    public_hex = private_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()

    print("=" * 78)
    print("Kortik Listener — Ed25519 par kljuceva")
    print("=" * 78)
    print()
    print("PUBLIC (ugradi u aplikaciju pri buildu):")
    print(public_hex)
    print()
    print("PRIVATE (samo server/CI, cuvaj kao tajnu):")
    print(private_hex)
    print()
    print("PowerShell:")
    print(f'  $env:LISTENER_UPDATE_PUBKEY = "{public_hex}"')
    print(f'  $env:LISTENER_UPDATE_SIGNING_KEY = "{private_hex}"')
    print()
    print("Backend .env (samo privatni, za potpisivanje manifesta):")
    print(f"  LISTENER_UPDATE_SIGNING_KEY={private_hex}")
    print()
    print("VAZNO: ako izgubis privatni kljuc, vise ne mozes da izdajes")
    print("azuriranja za vec instalirane aplikacije (moraju rucno da reinstaliraju).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

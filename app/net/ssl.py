# c:\Kortik\Kortik-Listener-App\app\net\ssl.py
"""
Zajednički TLS kontekst za sve HTTP klijente aplikacije.

Problem koji ovo rešava: na čistom Windows-u Pythonov `ssl.create_default_context()`
(a samim tim i aiohttp) NE čita Windows sertifikatski spremnik i NE povlači
automatski Mozilla CA bundle, pa HTTPS pozivi (npr. github.com) padaju sa
`CERTIFICATE_VERIFY_FAILED: unable to get local issuer certificate`.

Zato ovde gradimo kontekst koji:
  1. počinje od `ssl.create_default_context()` (TLS 1.2+),
  2. dodaje `certifi` CA bundle (Mozilla roots) kada je dostupan,
  3. dodaje Windows sistem sertifikate (korporativni MITM / antivirus roots).

Svaki pojedinačni sertifikat se učitava u sopstvenom `try/except`, tako da jedan
neispravan unos NE prekine kreiranje konteksta. Verifikacija sertifikata je uvek
uključena (`CERT_REQUIRED`) — nikad je ne gasimo.
"""
from __future__ import annotations

import logging
import ssl

logger = logging.getLogger("kortik.listener.net.ssl")

try:
    import certifi
except ImportError:  # pragma: no cover - certifi je u requirements i u buildu
    certifi = None


def _load_windows_certs(context: ssl.SSLContext) -> None:
    """Dodaje Windows sistem sertifikate (ROOT + CA) sa per-sertifikat obradom grešaka.

    `ssl.enum_certificates(store_name)` je stdlib (bez novih zavisnosti). Svaki
    pojedinačni sertifikat se učitava u sopstvenom try/except — jedan neispravan
    unos ne sme da prekine kreiranje konteksta.
    """
    enum = getattr(ssl, "enum_certificates", None)
    if not callable(enum):
        return

    pems = []
    for store_name in ("ROOT", "CA"):
        try:
            entries = enum(store_name)
        except Exception:  # pragma: no cover - store nedostupan / enum pali
            continue
        for entry in entries:
            try:
                der_bytes = entry[0]
                pems.append(ssl.DER_cert_to_PEM_cert(der_bytes))
            except Exception:
                continue  # preskoči neispravan sertifikat

    if pems:
        try:
            context.load_verify_locations(cadata="\n".join(pems))
        except Exception as e:  # pragma: no cover - zaštita od lošeg PEM-a
            logger.warning("Windows sertifikati nisu učitani: %s", e)


def create_client_ssl_context() -> ssl.SSLContext:
    """Vraća SSLContext za klijentske HTTPS pozive (aiohttp). Nikad ne diže izuzetak."""

    context = ssl.create_default_context()
    try:
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    except Exception:
        pass

    # 1) Mozilla CA bundle — popravlja nedostajuće javne CA na Windows-u.
    if certifi is not None:
        try:
            context.load_verify_locations(cafile=certifi.where())
        except Exception as e:  # pragma: no cover - zaštita od .where() grešaka
            logger.warning("certifi CA nije učitan: %s", e)

    # 2) Windows sistem sertifikati (korporativni MITM / antivirus roots).
    _load_windows_certs(context)

    return context
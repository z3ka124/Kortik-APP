# Kortik Listener (Windows aplikacija)

Desktop klijent preko koga **svaki korisnik** dobija svoj wake word i glasovne komande
za Kortik bota — bez drugog bota, bez Discord audio capture-a i bez deljenja bot tokena.

```
┌────────────── Korisnikov PC ──────────────┐
│ KortikListener.exe                        │
│  mikrofon → KWS "Kortik" → STT → parser   │
│  HMAC-potpisan HTTPS POST                 │
└───────────────────┬───────────────────────┘
                    │ TLS 1.3
┌───────────────────▼───────────────────────┐
│ Kortik backend  /api/listener/*           │
│  device auth + rate limit + audit         │
└───────────────────┬───────────────────────┘
                    │ 127.0.0.1 (HMAC)
┌───────────────────▼───────────────────────┐
│ Kortik bot (voice_bridge) → Lavalink      │
└───────────────────────────────────────────┘
```

## Privatnost

Aplikacija ne sadrži bot token ni lozinke Discord naloga — koristi se bezbedno uparivanje uređaja (6-cifreni kod sa dashboarda). Lokalne tajne su enkriptovane na računaru.

## Struktura

```
app/
  version.py              verzija, API URL, Ed25519 javni kljuc
  config.py               %LOCALAPPDATA% putanje + settings.json (bez tajni)
  logs.py                 rotacija + redakcija tajni
  core/parser.py          "pusti senidah" -> ("play", "senidah")
  security/dpapi.py       Windows DPAPI (ctypes, bez pywin32)
  security/storage.py     DPAPI-backed cuvanje tajni
  security/request_signer.py  HMAC potpis (identican backendu)
  net/api.py              aiohttp klijent (device flow, heartbeat, command, update)
  auth/device_flow.py     uparivanje + refresh rotacija
  updater/manifest.py     Ed25519 + SHA-256 verifikacija
  ui/main_window.py       PySide6 GUI (pairing, status, test komanda, log)
  main.py                 entrypoint + single instance
tests/                    49 testova (stdlib + cryptography), bez mreze
```

## Pokretanje (razvoj)

```powershell
cd c:\Kortik\Kortik-Listener-App
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.main
```

Ako PySide6 još nije instaliran, GUI neće startovati, ali **svi testovi rade**:

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

## Status po fazama

- [x] **M0** Bezbednosna sanacija (gitignore, `.env.example`, rotacija checklist, untrack tajni)
- [x] **M1** Backend gateway (device auth, HMAC, rate limit, audit, update manifest)
- [x] **M1.5** Bot strana (`/api/voice/from-user`, `/api/voice/user-state`, kulturni „zauzet“ odgovor)
- [x] **M2** App skeleton (pairing, DPAPI, HMAC klijent, GUI, parser, updater verifikacija)
- [x] **M3** Audio lanac: capture (`sounddevice`) → VAD → **Sherpa-ONNX KWS „Kortik“** → lokalni STT (`faster-whisper`)
- [x] **M5** Autostart (HKCU), „slušaj samo u VC“, log panel, graceful degradacija kad modeli nedostaju
- [x] **M6 (deo)** PyInstaller spec, Inno Setup, `sign.ps1`, `make_manifest.py`, GitHub Actions
- [x] **M4** Cloud STT (`/api/listener/transcribe` + Groq Whisper) i hibridni prekidač u UI-ju
- [x] **BETA** Dashboard stranica `/user/listener` (download + odobravanje koda + „Moji uređaji“)
- [ ] **M6 (ostatak)** Tray ikonica, model-pack downloader sa progresom, i18n dashboard stranice
- [ ] **M7** E2E QA na čistoj Windows VM (instalacija, update, busy scenario)

> **Za testiranje odmah:** vidi `BETA.md` — korak-po-korak scenario i tabela known-issues.

> Aplikacija radi i **bez** teških zavisnosti: ako `sounddevice`, `sherpa-onnx` ili
> `faster-whisper` nisu instalirani, UI to jasno prijavi, a login/status/test-komanda
> i dalje rade (graceful degradacija).

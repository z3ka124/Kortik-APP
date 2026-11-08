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

## Bezbednosni model (ukratko)

| Rizik | Kako je rešeno |
|---|---|
| Kradja bot tokena | **Bot token nikad nije u aplikaciji.** Muziku pušta centralni bot. |
| Lozinka Discord naloga | Ne koristi se. Samo device pairing (6-cifreni kod na dashboardu). |
| Krađa lokalnih tajni | `device_secret` i `refresh_token` su DPAPI-enkriptovani (`%LOCALAPPDATA%\Kortik\Listener\secrets.bin`). |
| Lažni zahtevi ka backendu | HMAC-SHA256 (`METHOD\|PATH\|TS\|NONCE\|SHA256(BODY)`) + timestamp ±60 s + nonce replay cache. |
| Replay / duplo puštanje | Nonce cache + idempotency `request_id`. |
| Zlonamerni update | Ed25519 potpis manifesta, HTTPS-only URL, SHA-256 fajla, blokada downgrade-a, Authenticode (M6). |
| Curenje tajni u logove | `app/logs.py` redaktuje tokene pre upisa. |
| Preterane permisije | Aplikacija radi bez admina; device JWT ima `type=device` i ne može na dashboard rute. |

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

## Backend ugovor (već implementirano u `Kortik-Dahabord-Backend`)

| Metoda | Ruta | Opis |
|---|---|---|
| POST | `/api/listener/auth/device/start` | `device_code` + `user_code` (10 min) |
| POST | `/api/listener/auth/device/approve` | dashboard potvrđuje `user_code` |
| POST | `/api/listener/auth/device/token` | tokeni + `device_secret` (jednom) |
| POST | `/api/listener/auth/device/refresh` | rotacija refresh tokena |
| POST | `/api/listener/heartbeat` | `in_voice`, `busy`, `plugin_enabled` |
| POST | `/api/listener/command` | glasovna komanda (HMAC) |
| POST | `/api/listener/transcribe` | cloud STT (Groq Whisper, HMAC, max 12 s) |
| GET | `/api/listener/version` | potpisan update manifest |
| GET/DELETE | `/api/listener/devices` | lista / opoziv uređaja |

Bot strana: `cogs/voice_bridge.py` → `/api/voice/from-user`, `/api/voice/user-state`
(oba zahtevaju interni HMAC `LISTENER_BRIDGE_SECRET`).

## Obavezna konfiguracija

Backend `.env`:

```ini
LISTENER_BRIDGE_SECRET=<64+ random znakova>   # isti kao u Kortik-Bot/config.env
LISTENER_BOT_API_URL=http://127.0.0.1:8088
LISTENER_APP_MANIFEST=listener_app_manifest.json
LISTENER_UPDATE_SIGNING_KEY=                  # Ed25519 privatni kljuc (samo server/CI)
KORTIK_OWNER_DISCORD_ID=<tvoj discord id>
```

`Kortik-Bot/config.env`:

```ini
LISTENER_BRIDGE_SECRET=<isti secret kao gore>
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

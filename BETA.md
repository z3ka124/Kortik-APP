# Kortik Listener — 1.0.0 BETA (vodič za testiranje)

> Cilj bete: da ti i par ljudi testirate **ceo lanac** — mikrofon → wake word → komanda → bot u VC-u.

---

## 1. Pre nego što pokreneš (5 minuta, jednom)

### a) Backend `.env`
```ini
LISTENER_BRIDGE_SECRET=<64+ random znakova>     # python -c "import secrets;print(secrets.token_urlsafe(64))"
LISTENER_BOT_API_URL=http://127.0.0.1:8088
KORTIK_OWNER_DISCORD_ID=<tvoj discord id>
LISTENER_APP_MANIFEST=listener_app_manifest.json
GROQ_API_KEY=<postoji već — koristi se za cloud STT>
```

### b) `Kortik-Bot/config.env`
```ini
LISTENER_BRIDGE_SECRET=<ISTI secret kao gore>
```

### c) Discord Developer Portal
*OAuth2 → Redirects* → dodaj: `http://127.0.0.1:47321/callback`

> Redirect za sada nije obavezan za device-pairing tok (koristi se 6-cifreni kod),
> ali ga dodaj da ne blokira kasniji „Login preko Discorda“.

### d) Restartuj backend i bota
Tabele `listener_*` se kreiraju same pri prvom zahtevu.

---

## 2. Instalacija aplikacije

```powershell
cd c:\Kortik\Kortik-Listener-App
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt      # PySide6, sounddevice, sherpa-onnx, faster-whisper…
python -m app.main
```

Prvi start može da potraje: `faster-whisper` skida model (~250 MB) pri **prvom**
prepoznavanju, ne pri pokretanju.

---

## 3. Test scenario (5 minuta)

| # | Radnja | Očekivano |
|---|---|---|
| 1 | Klikni **Upari uređaj** | pojavi se 6-cifreni kod + dugme ka dashboardu |
| 2 | Otvori `https://kortikbot.xyz/user/listener`, unesi kod, **Odobri** | app pređe na status ekran; u „Moji uređaji“ se pojavi tvoj PC |
| 3 | Uđi u voice kanal na Discord-u | u app-u „VC: *ime kanala*“ postaje zeleno |
| 4 | Klikni **Test komanda**, ukucaj `pusti senidah bez tebe` | bot uđe u tvoj VC i pusti pesmu; u app-u ✅ |
| 5 | Uključi **Slušam wake word „Kortik“** i kaži *„Kortik pusti …“* | app prikaže 👂 → 🎙️ → ✅ i pusti pesmu |
| 6 | Dok bot svira, neko iz drugog VC-a pozove bota | bot odgovori kulturno: „trenutno sviram u drugom kanalu…“ (i app prikaže ⚠️ busy) |

### Brzi testovi bez mikrofona
```powershell
python build\check_kws.py                 # model + pragovi + self-test
python build\check_kws.py --wav tvoj.wav  # tvoj snimak (16 kHz mono)
python -m unittest discover -s tests -p "test_*.py"
```

---

## 4. Šta je uključeno u betu

- ✅ Device pairing (6-cifreni kod), access/refresh tokeni, revoke po uređaju
- ✅ HMAC potpis svakog zahteva + replay zaštita + rate limit + audit log
- ✅ DPAPI čuvanje tajni, logovi sa redakcijom tokena
- ✅ Wake word **„Kortik“** (Sherpa-ONNX, model u repou)
- ✅ Lokalni STT (`faster-whisper`, privatno) **i** cloud STT (Groq Whisper preko backenda)
- ✅ Komande: play / pause / resume / skip / stop / volume
- ✅ „Slušaj samo dok sam u VC-u“, izbor mikrofona, jezik, osetljivost
- ✅ Autostart (HKCU), log panel, odjava uređaja
- ✅ Provera ažuriranja sa Ed25519 potpisom + SHA-256 + Authenticode proverom

## 5. Šta NIJE u beti (znaš da ne postoji)

- ❌ Tray ikonica (app mora da ostane otvoren)
- ❌ Gotov `.exe` installer — za betu se pokreće iz `python -m app.main`
  (build skripte postoje: `build/pyinstaller.spec`, `build/installer.iss`)
- ❌ Automatski download whisper modela sa progres barom (radi, ali tiho u pozadini)
- ❌ „Test mikrofona“ dugme (koristi `check_kws.py`)
- ❌ i18n dashboard stranice van sr/en

---

## 6. Rešavanje problema

| Simptom | Uzrok / rešenje |
|---|---|
| „Mikrofon nije dostupan“ | `pip install sounddevice` (PortAudio dolazi uz wheel) |
| „Sherpa KWS model nije pronađen“ | model je u `Kortik-VoiceListener/models/sherpa-kws`; ako si premestio repo, postavi `LOCALAPPDATA\Kortik\Listener\models\sherpa-kws` |
| `401 invalid_token` | upari ponovo (Sesija istekla) |
| `403 disabled` | Voice Commands plugin isključen za taj server (dashboard → Features) |
| `409 busy` | bot svira u drugom kanalu; sačekaj `retry_after` |
| `503 bridge_not_configured` | `LISTENER_BRIDGE_SECRET` nije isti u backendu i botu |
| `502 bot_unreachable` | bot nije pokrenut ili `voice_bridge` nije na 8088 |
| Update „odbijeno“ | `KORTIK_UPDATE_PUBKEY` u app-u mora odgovarati ključu kojim je manifest potpisan |
| Lažni wake word | smanji **Osetljivost wake word-a** u podešavanjima |

**Logovi:** `%LOCALAPPDATA%\Kortik\Listener\logs\listener.log`
(u app-u dugme „Osveži log“).

---

## 7. Prijava buga

Pošalji:
1. screenshot app-a (status linije su najbitnije)
2. zadnjih 30 linija `listener.log`
3. tačan izgovor (npr. „Kortik pusti Senidah bez tebe“)
4. da li je radio „Test komanda“ (kucanje) — to razdvaja problem mikrofona od problema bota

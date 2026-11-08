# Kortik Listener — kako napraviti `.exe` i objaviti prvu verziju

> Redosled je obavezan. Sve komande se pokreću u **PowerShell** (Win 10/11 x64).
> Prvi build mora da se uradi na tvojoj mašini — u pripremi ovog repoa nisu bili
> instalirani `PySide6`, `PyInstaller` ni `Inno Setup`.

---

## 0. Preduslovi (jednom)

| Alat | Verzija | Provera |
|---|---|---|
| Windows | 10/11 x64 | `[Environment]::Is64BitOperatingSystem` |
| Python | 3.11 – 3.13 | `python --version` |
| Inno Setup | 6.x | `Test-Path "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"` |
| Git | bilo koja | `git --version` |
| (opciono) EV code-signing sertifikat | `.pfx` + lozinka | za SmartScreen bez upozorenja |

Instalacija Inno Setup-a: <https://jrsoftware.org/isdl.php> (Next → Next → Install).

---

## 1. Pripremi Python okruženje za build

```powershell
cd c:\Kortik\Kortik-Listener-App
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
pip install pyinstaller
```

Provera da je sve tu:

```powershell
python -c "import PySide6, aiohttp, cryptography, sounddevice, sherpa_onnx, faster_whisper; print('OK')"
python build\check_kws.py        # mora da ispiše "Model ispravno detektuje svoje test reči."
```

---

## 2. Generiši Ed25519 ključeve za ažuriranja (jednom, čuvaj zauvek)

```powershell
python build\keygen.py
```

Dobijaš dva heksadecimalna ključa:

| Ključ | Gde ide | Nikad |
|---|---|---|
| **PUBLIC** (64 znaka) | u `.exe` pri buildu (`LISTENER_UPDATE_PUBKEY`) | — |
| **PRIVATE** (64 znaka) | samo server/CI (`LISTENER_UPDATE_SIGNING_KEY`) | ❌ ne u git, ne u app, ne u chat |

Sačuvaj privatni ključ u password manager. **Ako ga izgubiš, nema više update-a** za instalirane app-ove.

---

## 3. Podesi backend (server gde radi `main.py`)

U `Kortik-Bot Dashabord/Kortik-Dahabord-Backend/.env`:

```ini
LISTENER_BRIDGE_SECRET=<64+ random>        # python -c "import secrets;print(secrets.token_urlsafe(64))"
LISTENER_BOT_API_URL=http://127.0.0.1:8088
KORTIK_OWNER_DISCORD_ID=<tvoj discord id>
LISTENER_APP_MANIFEST=listener_app_manifest.json
LISTENER_UPDATE_SIGNING_KEY=<PRIVATE kljuc iz koraka 2>
LISTENER_UPDATE_PUBKEY=<PUBLIC kljuc>       # samo za evidenciju/dijagnostiku
GROQ_API_KEY=<postoji>                      # potreban za cloud STT
```

Restartuj backend. Tabele se kreiraju same na prvi zahtev (`listener_pairing`, `listener_devices`, `listener_audit`).

Brza provera sa servera:

```bash
curl -s https://api.kortikbot.xyz/api/listener/version | head -c 200
# 404 manifest_not_configured = OK (još nema manifesta)
```

## 4. Podesi bota (isti server)

`Kortik-Bot/config.env`:

```ini
LISTENER_BRIDGE_SECRET=<ISTI secret kao u backendu>
```

Restartuj bota. U logu mora da piše:

```
Legacy Voice Listener je isključen — koristi se Kortik Listener (desktop app).
✅ Voice Bridge API aktivan na http://127.0.0.1:8088
```

---

## 5. Napravi `.exe` i installer

```powershell
cd c:\Kortik\Kortik-Listener-App
.\.venv\Scripts\Activate.ps1

# PUBLIC kljuc iz koraka 2 (obavezno, inace .exe ne verifikuje update)
$env:LISTENER_UPDATE_PUBKEY = "<64 hex PUBLIC>"

.\build\build.ps1 -Version 1.0.0 -CdnBase "https://cdn.kortikbot.xyz/listener"
```

Skripta radi redom: zavisnosti → **107 testova** → upis javnog ključa → PyInstaller →
Inno Setup → (ako je postavljen `LISTENER_UPDATE_SIGNING_KEY`) potpisan manifest.

Rezultat:

```
build\output\KortikListener\KortikListener.exe          ← portable verzija (folder se ne razdvaja!)
build\output\installer\KortikListener-1.0.0-setup.exe   ← ovo se deli korisnicima
listener_app_manifest.json                              ← samo ako je postavljen signing kljuc
```

### Ako Inno Setup nije instaliran
Skripta napravi `build\output\KortikListener-1.0.0-win64.zip` i nastavi — installer možeš dodati kasnije.

### Brzi „smoke test“ pre deljenja

```powershell
# 1) pokreni portable build i proveri da se otvara
Start-Process "build\output\KortikListener\KortikListener.exe"

# 2) proveri da su model i keywords unutra (mora da ih nadje)
Get-ChildItem "build\output\KortikListener\_internal\models\sherpa-kws" | Select-Object Name
Get-ChildItem "build\output\KortikListener\_internal\app\kws" | Select-Object Name
```

---

## 6. Potpiši installer (Authenticode) — opciono, ali preporučeno

Bez potpisa korisnici vide „Windows protected your PC“ (više klikova, deluje sumnjivo).

```powershell
$env:SIGN_CERT_PATH     = "C:\secrets\kortik-ev.pfx"
$env:SIGN_CERT_PASSWORD = "<lozinka>"
.\build\sign.ps1 -Version 1.0.0
```

Skripta potpisuje i `KortikListener.exe` i installer, pa verifikuje potpis.

> Bez EV sertifikata: preskoči ovaj korak. Aplikacija i dalje radi, samo SmartScreen upozorava.

---

## 7. Okači installer (CDN / hosting)

Bilo koji od tri načina — bitno je da URL bude **HTTPS** i da vodi direktno na `.exe`:

**A) Cloudflare R2 / S3 (preporučeno)**
```powershell
# bucket: kortik-cdn, folder: listener/
aws s3 cp "build\output\installer\KortikListener-1.0.0-setup.exe" `
    s3://kortik-cdn/listener/ --endpoint-url https://<r2-endpoint> `
    --content-type application/vnd.microsoft.portable-executable
```

**B) nginx na tvom serveru**
```bash
mkdir -p /var/www/cdn/listener
cp KortikListener-1.0.0-setup.exe /var/www/cdn/listener/
# nginx: location /listener/ { alias /var/www/cdn/listener/; }
```

**C) GitHub Release (najjednostavnije za betu)**
```powershell
git tag listener-v1.0.0
git push origin listener-v1.0.0
# zatim na GitHub-u: Releases → Draft new release → izaberi tag → upload .exe
```

Provera da link radi (mora vratiti 200 i veličinu):
```powershell
$url = "https://cdn.kortikbot.xyz/listener/KortikListener-1.0.0-setup.exe"
(Invoke-WebRequest $url -Method Head).Headers['Content-Length']
```

---

## 8. Napravi update manifest i stavi ga na server

```powershell
cd c:\Kortik\Kortik-Listener-App
$env:LISTENER_UPDATE_SIGNING_KEY = "<64 hex PRIVATE>"   # sa servera, ne iz gita

python build\make_manifest.py `
    --installer "build\output\installer\KortikListener-1.0.0-setup.exe" `
    --version 1.0.0 `
    --min-version 1.0.0 `
    --url "https://cdn.kortikbot.xyz/listener/KortikListener-1.0.0-setup.exe" `
    --notes "Prva javna verzija" `
    --out listener_app_manifest.json
```

Kopiraj `listener_app_manifest.json` **pored `main.py`** na serveru, pa restartuj backend.

Provera:
```bash
curl -s https://api.kortikbot.xyz/api/listener/version
# { "version": "1.0.0", ..., "sha256": "...", "sig": "..." }
```

> `sig` postoji == manifest je potpisan. Aplikacije bez potpisa update **odbijaju** (to je namerno).

---

## 9. Podesi dashboard (frontend) i objavi stranicu

U `Kortik-Bot Dashabord/Kortik-Dahabord-Fronted/.env` (ili `.env.local`):

```ini
NEXT_PUBLIC_LISTENER_DOWNLOAD_URL="https://cdn.kortikbot.xyz/listener/KortikListener-1.0.0-setup.exe"
NEXT_PUBLIC_LISTENER_VERSION="1.0.0"
```

Rebuild + deploy:

```powershell
cd "c:\Kortik\Kortik-Bot Dashabord\Kortik-Dahabord-Fronted"
npm ci
npm run build
# zavisno od hostinga: vercel --prod   ili   pm2 restart kortik-frontend
```

> Next.js čita `NEXT_PUBLIC_*` **u build-time**. Ako promeniš URL bez rebuild-a, dugme ostaje staro.

Stranica za korisnike: **`https://kortikbot.xyz/user/listener`**
- kartica 1: download dugme
- kartica 2: unos 6-cifrenog koda
- kartica 3: „Moji uređaji“ + revoke

---

## 10. Verifikacija pre nego što pustiš ljudima (12 tačaka)

| # | Provera | Očekivano |
|---|---|---|
| 1 | `pip install -r requirements.txt` na čistoj VM | prolazi bez greške |
| 2 | Pokretanje `KortikListener.exe` | otvori se prozor, u logu „API: https://api.kortikbot.xyz“ |
| 3 | „Upari uređaj“ | prikaže se 6-cifreni kod |
| 4 | `/user/listener` → unos koda → Odobri | app pređe na status, uređaj u listi |
| 5 | Ulazak u VC | „VC: …“ zeleno u app-u |
| 6 | „Test komanda“: `pusti senidah bez tebe` | bot uđe i pusti pesmu |
| 7 | Wake word: „Kortik pusti senidah“ | 👂 → 🎙️ → ✅ + muzika |
| 8 | Zauzet scenario (dva VC-a) | kulturna poruka + `retry_after` |
| 9 | `build\check_kws.py --wav tvoj.wav` | detektuje Kortik |
| 10 | Isključi net → pokreni app | radi (update check fail-open) |
| 11 | Ručno pokvari manifest (`"sig": "00…"`) | app prikaže „Ažuriranje odbijeno“ |
| 12 | Dashboard → Ukloni uređaj | app dobije 401/403 i traži ponovno uparivanje |

---

## 11. Sledeća verzija (1.0.1, 1.1.0 …)

```powershell
# 1) podigni verziju u app/version.py (ili preko env-a pri buildu)
#    APP_VERSION = "1.0.1"
# 2) build + potpis + manifest (isti koraci 5, 6, 8) sa novim brojem
# 3) upload novog .exe-a (stari NE briši — neko može da ima staru verziju)
# 4) novi manifest zameni na serveru
# 5) objavi release notes
```

Klijenti na startu vide novu verziju → potpis se verifikuje → `sha256` → Authenticode →
`/SILENT` install → app se restartuje. `min_version` u manifestu tera **obavezan** update
(blokira stare verzije koje imaju bezbednosni problem).

CI varijanta (bez tvoje mašine): `.github/workflows/listener-app.yml` — tag `listener-v1.0.1`
pokreće testove, build, potpis (ako su postavljeni `SIGN_CERT_BASE64`, `SIGN_CERT_PASSWORD`,
`LISTENER_UPDATE_SIGNING_KEY`) i pravi artefakte.

---

## 12. Rollback (ako objaviš lošu verziju)

1. Vrati **prethodni** `listener_app_manifest.json` na server (i restartuj backend).
2. Novi klijenti dobijaju staru (ispravnu) verziju; oni koji su već instalirali lošu —
   objavi `min_version` hitfix i obavesti ih.
3. U aplikaciji: „Odjavi uređaj“ briše lokalne kredencijale; dashboard omogućava revoke po uređaju.
4. Loš `.exe` **ne briši** sa CDN-a dok ne prođe 30 dana (update linkovi u kešu).

---

## 13. Šta NIKAD ne raditi

- ❌ Ne stavljaj bot token, `DISCORD_CLIENT_SECRET` ili privatni Ed25519 ključ u aplikaciju ili repo.
- ❌ Ne objavljuj nepotpisan manifest (app će ga odbiti, ali bolje ga ni ne praviti).
- ❌ Ne koristi HTTP za download (updater odbija `http://`).
- ❌ Ne menjaj `LISTENER_BRIDGE_SECRET` samo na jednoj strani (bot vrati 503 `bridge_not_configured`).
- ❌ Ne briši stare instalere sa CDN-a (update na staru verziju mora da radi).
- ❌ Ne deli `client_secret` — device pairing postoji baš zato da ne mora.


### Ako Inno Setup nije instaliran
Skripta napravi `build\output\KortikListener-1.0.0-win64.zip` i nastavi — installer možeš dodati kasnije.

### Bezbednosna provera pre deljenja

```powershell
Get-AuthenticodeSignature "build\output\installer\KortikListener-1.0.0-setup.exe" | Select-Object Status
```
`Status` mora biti `Valid` **ako** si potpisao (korak 6). Ako nisi, Windows će prikazati SmartScreen upozorenje — to je normalno za nepotpisan build.

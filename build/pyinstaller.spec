# -*- mode: python ; coding: utf-8 -*-
# c:\Kortik\Kortik-Listener-App\build\pyinstaller.spec
"""
PyInstaller spec (onedir, windowed).

Build:
    pyinstaller build/pyinstaller.spec --noconfirm --clean --distpath build/output --workpath build/work
"""
import os
import sys

from PyInstaller.utils.hooks import collect_all

APP_NAME = "KortikListener"
def _detect_project_root() -> str:
    """
    PyInstaller ne daje SPECPATH pouzdano kroz sve verzije, pa root trazimo
    po markeru `app/main.py` (umesto da pogadjamo broj `..`).
    """
    override = os.environ.get("KORTIK_APP_ROOT", "").strip()
    candidates = []
    if override:
        candidates.append(override)

    spec_file = globals().get("SPEC")
    if spec_file:
        candidates.append(os.path.dirname(os.path.dirname(os.path.abspath(spec_file))))

    specpath = globals().get("SPECPATH")
    if specpath:
        candidates.append(os.path.abspath(specpath))
        candidates.append(os.path.dirname(os.path.abspath(specpath)))

    candidates.append(os.getcwd())

    for candidate in candidates:
        if not candidate:
            continue
        if os.path.isfile(os.path.join(candidate, "app", "main.py")):
            return os.path.abspath(candidate)

    raise SystemExit(
        "[spec] Ne mogu da nadjem projektni root (trazim app/main.py).\n"
        "       Resi:  $env:KORTIK_APP_ROOT = 'C:\\Kortik\\Kortik-Listener-App'"
    )


PROJECT_ROOT = _detect_project_root()
os.chdir(PROJECT_ROOT)
print(f"[spec] PROJECT_ROOT = {PROJECT_ROOT}")

datas = []
binaries = []
hiddenimports = ["app.main"]

for package in ("sherpa_onnx", "faster_whisper", "ctranslate2", "aiohttp", "certifi", "_sounddevice_data"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception as exc:  # paket nije instaliran ili nije package
        print(f"[spec] collect_all({package}) preskocen: {exc}")

icon_path = os.path.join(PROJECT_ROOT, "assets", "icon.ico")
icon = icon_path if os.path.exists(icon_path) else None

# ─── Bundled resursi (obavezno za .exe) ─────────────────────────────────────
# 1) Kalibrisani wake word fajl
keywords_src = os.path.join(PROJECT_ROOT, "app", "kws", "keywords_kortik.txt")
if os.path.exists(keywords_src):
    datas.append((keywords_src, os.path.join("app", "kws")))

# 2) Javni Ed25519 kljuc za update (upisuje ga build/build.ps1)
pubkey_src = os.path.join(PROJECT_ROOT, "app", "update_pubkey.txt")
if os.path.exists(pubkey_src):
    datas.append((pubkey_src, "app"))

# 3) Sherpa KWS model (int8, ~5.3 MB) — bez ovoga .exe nema wake word
MODEL_FILES = (
    "tokens.txt",
    "bpe.model",
    "encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
    "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx",
)
model_candidates = [
    os.environ.get("KORTIK_KWS_MODEL", ""),
    os.path.join(PROJECT_ROOT, "models", "sherpa-kws"),
    os.path.join(PROJECT_ROOT, "..", "Kortik-VoiceListener", "models", "sherpa-kws"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Kortik", "Listener", "models", "sherpa-kws"),
]
model_found = False
for candidate in model_candidates:
    if not candidate or not os.path.isdir(candidate):
        continue
    present = [name for name in MODEL_FILES if os.path.exists(os.path.join(candidate, name))]
    if len(present) < len(MODEL_FILES):
        continue
    for name in MODEL_FILES:
        datas.append((os.path.join(candidate, name), os.path.join("models", "sherpa-kws")))
    model_found = True
    print(f"[spec] Sherpa KWS model ukljucen iz: {candidate}")
    break

if not model_found:
    print("[spec] UPOZORENJE: Sherpa KWS model nije pronadjen — .exe nece imati wake word!")

a = Analysis(
    [os.path.join(PROJECT_ROOT, "app", "main.py")],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pandas", "scipy", "notebook", "IPython"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=icon,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)

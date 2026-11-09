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
hiddenimports = [
    "app.main",
    "openwakeword",
    "openwakeword.model",
    "openwakeword.utils",
    "openwakeword.vad",
    "openwakeword.custom_verifier_model",
    "openwakeword.data",
]

for package in ("faster_whisper", "ctranslate2", "onnxruntime", "aiohttp", "certifi", "_sounddevice_data"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
        datas += pkg_datas
        binaries += pkg_binaries
        hiddenimports += pkg_hidden
    except Exception as exc:  # paket nije instaliran ili nije package
        print(f"[spec] collect_all({package}) preskocen: {exc}")

icon_path = os.path.join(PROJECT_ROOT, "assets", "icon.ico")
icon = icon_path if os.path.exists(icon_path) else None
if icon:
    # ikonica i u bundle-u (da je app moze postaviti kao window icon)
    datas.append((icon_path, "assets"))

# ─── Bundled resursi (obavezno za .exe) ─────────────────────────────────────
# 2) Javni Ed25519 kljuc za update (upisuje ga build/build.ps1)
pubkey_src = os.path.join(PROJECT_ROOT, "app", "update_pubkey.txt")
if os.path.exists(pubkey_src):
    datas.append((pubkey_src, "app"))

# 2b) Verzija upisana pri buildu (da frozen app prijavi TACNU verziju)
buildver_src = os.path.join(PROJECT_ROOT, "app", "_build_version.txt")
if os.path.exists(buildver_src):
    datas.append((buildver_src, "app"))

# 3) OpenWakeWord model (hey_jarvis + melspectrogram + embedding) — bez ovoga nema wake word
OWW_MODEL_FILES = ("hey_jarvis_v0.1.onnx", "melspectrogram.onnx", "embedding_model.onnx")
oww_model_dir = os.path.join(PROJECT_ROOT, "models", "openwakeword")
if os.path.isdir(oww_model_dir) and all(
    os.path.exists(os.path.join(oww_model_dir, name)) for name in OWW_MODEL_FILES
):
    for name in OWW_MODEL_FILES:
        datas.append((os.path.join(oww_model_dir, name), os.path.join("models", "openwakeword")))
    print(f"[spec] OpenWakeWord model ukljucen iz: {oww_model_dir}")
else:
    print("[spec] UPOZORENJE: OpenWakeWord model nije pronadjen — .exe nece imati wake word!")

a = Analysis(
    [os.path.join(PROJECT_ROOT, "app", "main.py")],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pandas", "notebook", "IPython"],
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

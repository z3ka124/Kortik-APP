# c:\Kortik\Kortik-Listener-App\tools\audit_app.py
"""
Audit cele Kortik Listener aplikacije (bez mreze, bez GUI-ja).

    python tools\\audit_app.py

Proverava: py_compile, import svih modula, UI kontrole, frozen putanje,
wake word konfiguraciju, update manifest i build artefakte.
"""
from __future__ import annotations

import json
import py_compile
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(ok), detail))


def main() -> int:
    # 1) py_compile svih .py fajlova
    broken = []
    for path in list((PROJECT_ROOT / "app").rglob("*.py")) + list((PROJECT_ROOT / "tests").rglob("*.py")):
        try:
            py_compile.compile(str(path), doraise=True)
        except Exception as exc:
            broken.append(f"{path.name}: {exc}")
    check("py_compile (app + tests)", not broken, "; ".join(broken[:3]))

    # 2) import svih modula aplikacije
    modules = [
        "app.config", "app.version", "app.logs",
        "app.core.parser", "app.core.listener_core", "app.core.listener_service",
        "app.audio.vad", "app.audio.capture",
        "app.kws.openwakeword_kws", "app.stt.base", "app.stt.cloud", "app.stt.local_whisper",
        "app.stt.wav", "app.updater.manifest", "app.updater.installer",
        "app.system.autostart", "app.net.api", "app.auth.device_flow",
        "app.security.dpapi", "app.security.storage", "app.security.request_signer",
    ]
    failed = []
    for name in modules:
        try:
            __import__(name)
        except Exception as exc:
            failed.append(f"{name}: {type(exc).__name__}: {exc}")
    check(f"import {len(modules)} modula", not failed, "; ".join(failed[:3]))

    # 3) UI kontrole (staticka provera izvora)
    ui = (PROJECT_ROOT / "app" / "ui" / "main_window.py").read_text(encoding="utf-8")
    for control, label in (
        ("mic_combo", "izbor mikrofona"),
        ("mic_test_btn", "test mikrofona"),
        ("listen_btn", "dugme za slusanje"),
        ("listen_check", "checkbox slusanja"),
        ("model_size_combo", "STT model size dropdown"),
        ("cloud_model_combo", "cloud STT model dropdown"),
        ("_reload_mics", "osvezavanje liste mikrofona"),
    ):
        check(f"UI: {label}", control in ui)

    check("UI: nema setEnabled(False) na listen", "listen_check.setEnabled(False)" not in ui)
    check("UI: wake word je uvek OWW (nema wake_combo)", "wake_combo" not in ui)
    check("UI: tekst ceka 'Hey Jarvis'", "čekam „Hey Jarvis" in ui)
    check("UI: log sekcija uklonjena", "log_view" not in ui and "Osveži log" not in ui)
    check(
        "Config: stt_cloud_model",
        "stt_cloud_model" in (PROJECT_ROOT / "app" / "config.py").read_text(encoding="utf-8"),
    )

    # 4) wake word konfiguracija (OpenWakeWord)
    from app.kws.openwakeword_kws import default_model_dir, threshold_from_sensitivity

    model_dir = default_model_dir()
    model_present = (model_dir / "hey_jarvis_v0.1.onnx").exists() and (
        model_dir / "melspectrogram.onnx"
    ).exists() and (model_dir / "embedding_model.onnx").exists()
    check("OWW: model pronadjen", model_present, str(model_dir))
    low, mid = threshold_from_sensitivity(0.0), threshold_from_sensitivity(0.5)
    check(
        "OWW: prag iz klizaca",
        0.0 < low <= 1.0 and 0.0 < mid <= 1.0 and low >= mid,
        f"0.0->{low} · 0.5->{mid}",
    )

    # 5) engine dostupan (onnxruntime + openwakeword)
    from app.kws.openwakeword_kws import OpenWakeWordKws

    check("OWW: engine dostupan", OpenWakeWordKws.available(model_dir))

    # 6) update (manifest + javni kljuc)
    from app.updater.manifest import verify_signature
    pubkey_path = PROJECT_ROOT / "app" / "update_pubkey.txt"
    pubkey = pubkey_path.read_text(encoding="utf-8").strip() if pubkey_path.exists() else ""
    check("Update: javni kljuc ugrađen", len(pubkey) == 64, pubkey[:16] + "..." if pubkey else "nema")

    manifest_path = PROJECT_ROOT / "listener_app_manifest.json"
    if manifest_path.exists() and pubkey:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        ok, reason = verify_signature(manifest, pubkey)
        check("Update: manifest potpisan", ok, reason)
    else:
        check("Update: manifest", manifest_path.exists(), "nije nadjen (opciono)")

    # 7) build artefakti
    version = __import__("app.version", fromlist=["APP_VERSION"]).APP_VERSION
    exe = PROJECT_ROOT / "build" / "output" / "KortikListener" / "KortikListener.exe"
    installer_dir = PROJECT_ROOT / "build" / "output" / "installer"
    installers = sorted(installer_dir.glob("*.exe")) if installer_dir.exists() else []
    check("Build: EXE postoji", exe.exists(), f"{exe.stat().st_size // (1024*1024)} MB" if exe.exists() else "nema")
    check("Build: installer postoji", bool(installers), installers[-1].name if installers else "nema")
    check("Build: ikonica", (PROJECT_ROOT / "assets" / "icon.ico").exists())
    check("Verzija u kodu", True, version)

    # 8) izlaz
    width = max(len(name) for name, _, _ in RESULTS) + 2
    failed_count = 0
    print()
    for name, ok, detail in RESULTS:
        status = "PASS" if ok else "FAIL"
        if not ok:
            failed_count += 1
        print(f"[{status}] {name:<{width}} {detail}")
    print()
    print(f"UKUPNO: {len(RESULTS)} | FAIL: {failed_count}")
    return 1 if failed_count else 0


if __name__ == "__main__":
    raise SystemExit(main())

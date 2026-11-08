# c:\Kortik\Kortik-Listener-App\build\check_kws.py
"""
Dijagnostika wake word modela (bez mikrofona).

Pokreni iz Kortik-Listener-App:
    python build/check_kws.py
    python build/check_kws.py --wav "C:\\neki\\snimak.wav" --threshold 0.2

Proverava:
  1. da li je sherpa-onnx instaliran
  2. da li je model „Kortik“ kompletan
  3. da li se wake word detektuje u test WAV fajlovima
"""
from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.kws.sherpa_kws import (  # noqa: E402
    SherpaKws,
    default_keywords_file,
    default_model_dir,
    threshold_from_sensitivity,
)

CHUNK_BYTES = 640


def scan_wav(kws: SherpaKws, path: Path) -> str:
    with wave.open(str(path), "rb") as handle:
        rate = handle.getframerate()
        channels = handle.getnchannels()
        data = handle.readframes(handle.getnframes())

    if channels != 1 or rate != 16000:
        return f"preskočeno (rate={rate}, channels={channels})"

    kws.load()
    for offset in range(0, len(data) - CHUNK_BYTES, CHUNK_BYTES):
        result = kws.process(data[offset: offset + CHUNK_BYTES])
        if result:
            return f"DETEKTOVANO: {result}"
    return "nema detekcije"


def self_test(model_dir: Path) -> int:
    """
    Provera da sam model radi: koristi keyworde koje model dobija uz sebe
    (`test_wavs/test_keywords.txt` + `test_wavs/*.wav`).
    """
    test_dir = model_dir / "test_wavs"
    keywords = test_dir / "test_keywords.txt"
    wavs = sorted(test_dir.glob("*.wav"))
    if not keywords.exists() or not wavs:
        print("Self-test preskočen (nema test_wavs/test_keywords.txt).")
        return 0

    print("\n=== SELF-TEST MODELA (test_wavs) ===")
    kws = SherpaKws(model_dir=model_dir, keywords_file=keywords, threshold=0.20)
    failures = 0
    for wav in wavs:
        outcome = scan_wav(kws, wav)
        print(f"  {wav.name:12} {outcome}")
        if not outcome.startswith("DETEKTOVANO"):
            failures += 1

    if failures:
        print(f"  ⚠ {failures}/{len(wavs)} test fajlova nije detektovano (model/prag).")
    else:
        print("  ✅ Model ispravno detektuje svoje test reči.")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav", action="append", default=[], help="Snimak za proveru (16 kHz mono)")
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--sensitivity", type=float, default=0.5)
    parser.add_argument("--keywords-file", default=None)
    parser.add_argument("--skip-self-test", action="store_true")
    args = parser.parse_args()

    model_dir = default_model_dir()
    threshold = args.threshold if args.threshold is not None else threshold_from_sensitivity(args.sensitivity)

    print(f"Model:      {model_dir}")
    print(f"Threshold:  {threshold}")

    try:
        import sherpa_onnx
    except ImportError:
        print("GREŠKA: sherpa-onnx nije instaliran (pip install sherpa-onnx).")
        return 2

    print(f"sherpa-onnx: {sherpa_onnx.__version__}")

    if not SherpaKws.available(model_dir):
        print("GREŠKA: model nije kompletan (tokens.txt + encoder/decoder/joiner).")
        return 3

    if not args.skip_self_test:
        self_test(model_dir)

    keywords_file = Path(args.keywords_file) if args.keywords_file else default_keywords_file()
    print(f"\n=== KORTIK KEYWORDS ({keywords_file.name}) ===")
    try:
        for line in keywords_file.read_text(encoding="utf-8").splitlines():
            if line.strip():
                print(f"  {line}")
    except Exception as e:
        print(f"  GREŠKA: ne mogu da pročitam keywords fajl: {e}")
        return 4

    if not args.wav:
        print("\nZa proveru svog snimka: python build/check_kws.py --wav putanja.wav")
        return 0

    print("\n=== PROVERA SNIMAKA (Kortik keywords) ===")
    kws = SherpaKws(model_dir=model_dir, keywords_file=keywords_file, threshold=threshold)
    for wav in [Path(p) for p in args.wav]:
        print(f"  {wav.name:32} {scan_wav(kws, wav)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

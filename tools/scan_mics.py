# c:\Kortik\Kortik-Listener-App\tools\scan_mics.py
"""
Testira sve ulazne uredjaje i ispise peak RMS (dijagnostika mikrofona).

    python tools\\scan_mics.py
    python tools\\scan_mics.py --seconds 2

Pokreni i PRICAJ tokom skeniranja — uredjaj sa najvecim RMS-om je pravi.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.audio.capture import MicrophoneCapture, list_input_devices  # noqa: E402
from app.audio.vad import rms  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, default=1.5)
    args = parser.parse_args()

    devices = list_input_devices()
    print(f"Ulaznih uredjaja: {len(devices)}\n")
    results = []

    for device in devices:
        capture = MicrophoneCapture(device=str(device["index"]))
        peak = 0
        try:
            capture.start()
            deadline = time.monotonic() + args.seconds
            while time.monotonic() < deadline:
                chunk = capture.read(0.1)
                if chunk:
                    peak = max(peak, int(rms(chunk)))
            results.append((peak, device["name"], capture.device_label))
            print(f"{peak:>6}  {device['name'][:48]}  (label={capture.device_label[:28]})")
        except Exception as exc:
            print(f"   ERR  {device['name'][:48]}  {exc}")
        finally:
            try:
                capture.stop()
            except Exception:
                pass

    if results:
        best = max(results)
        print(f"\nNAJBOLJI: RMS={best[0]}  {best[1]}")
        print("Ako je i najbolji < 50: proveri Windows postavke privatnosti mikrofona")
        print("(Settings → Privacy → Microphone → Allow desktop apps).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

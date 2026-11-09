# -*- coding: utf-8 -*-
"""
OpenWakeWord provera na realnim .wav uzorcima („Hey Jarvis").

    python tools\\test_oww_phrase.py
    python tools\\test_oww_phrase.py --threshold 0.35 --dir c:\\Kortik\\Kortik-VoiceListener
"""
from __future__ import annotations

import argparse
import sys
import wave
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np  # noqa: E402

from app.kws.openwakeword_kws import OpenWakeWordKws  # noqa: E402


def load_wav(path: Path):
    with wave.open(str(path), "rb") as wav:
        frames = wav.getnframes()
        channels = wav.getnchannels()
        raw = wav.readframes(frames)
    data = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1).astype(np.int16)
    return data.tobytes()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.4)
    parser.add_argument(
        "--dir",
        default=str(PROJECT_ROOT.parent / "Kortik-VoiceListener"),
    )
    args = parser.parse_args()

    if not OpenWakeWordKws.available():
        print("OpenWakeWord nije dostupan (pip install openwakeword).")
        return 1

    kws = OpenWakeWordKws(threshold=args.threshold)
    kws.load()
    print(f"OpenWakeWord spreman (prag={kws.threshold}).\n")

    base = Path(args.dir)
    wavs = sorted(base.glob("test_*.wav"))
    for path in wavs:
        pcm = load_wav(path)
        kws.reset()
        score = kws.peak_score(pcm)
        hit = "DETEKTUJE [OK]" if score >= kws.threshold else "nema"
        print(f"{score:.3f}  {hit:14s}  {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
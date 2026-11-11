# c:\Kortik\Kortik-Listener-App\app\audio\sounds.py
"""Prijatni, kratki zvučni efekti (bez spoljnih asset-a i bez novih zavisnosti).

Dva RAZLIČITA zvuka:
  * wake    — meki "ding-dong" (rastuća dva tona) kad se aktivira wake word / trigger
  * command — svetli kratki "ting" kad je komanda prepoznata

Talasni oblici se sintetizuju u %TEMP% kao 16-bit mono WAV i puštaju preko
`winsound` (Windows, SND_ASYNC), pa ništa ne blokira UI.
"""
from __future__ import annotations

import math
import os
import struct
import tempfile
from typing import List, Optional, Tuple

try:  # Windows only — app je win-x64, ali da import ne koči testove
    import winsound
except ImportError:  # pragma: no cover
    winsound = None  # type: ignore

_SAMPLE_RATE = 22050
_cache = {}


def _synthesize(path: str, steps: List[Tuple[float, float]], volume: float = 0.5) -> None:
    """Napiše WAV; steps = [(frekvenca_hz, trajanje_s)]. Envelope = mekano smirivanje."""
    total = sum(d for _f, d in steps)
    n = int(_SAMPLE_RATE * total)
    with open(path, "wb") as out:
        out.write(b"RIFF")
        data_size = n * 2
        out.write(struct.pack("<I", 36 + data_size))
        out.write(b"WAVEfmt ")
        out.write(struct.pack("<IHHIIHH", 16, 1, 1, _SAMPLE_RATE, _SAMPLE_RATE * 2, 2, 16))
        out.write(b"data")
        out.write(struct.pack("<I", data_size))
        t = 0.0
        for freq, dur in steps:
            step_n = int(_SAMPLE_RATE * dur)
            for i in range(step_n):
                local = i / _SAMPLE_RATE
                # eksponencijalno smirivanje + blag napad da ne "klikne" na početku
                amp = volume * math.exp(-3.0 * (t + local) / max(total, 1e-6))
                attack = min(1.0, (local / max(0.005, dur)) * 4.0)
                sample = int(32767 * amp * attack * math.sin(2 * math.pi * freq * local))
                out.write(struct.pack("<h", sample))
            t += dur


def _ensure(name: str) -> Optional[str]:
    if name in _cache:
        return _cache[name]
    path = os.path.join(tempfile.gettempdir(), f"kortik_listener_{name}.wav")
    try:
        if not os.path.exists(path):
            if name == "wake":
                # rastuća dva tona: E5 (659 Hz) -> G5 (784 Hz)
                _synthesize(path, [(659.0, 0.16), (784.0, 0.22)])
            else:
                # svetli kratki "ting": A5 (880 Hz)
                _synthesize(path, [(880.0, 0.18)])
    except Exception:
        return None
    _cache[name] = path
    return path


def _play(name: str) -> None:
    if winsound is None:
        return
    path = _ensure(name)
    if not path:
        return
    try:
        winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC)
    except Exception:
        pass


def play_wake() -> None:
    _play("wake")


def play_command() -> None:
    _play("command")
# c:\Kortik\Kortik-Listener-App\app\stt\wav.py
"""PCM (int16 mono) -> WAV bytes, bez zavisnosti."""
from __future__ import annotations

import io
import wave

DEFAULT_RATE = 16000


def pcm_to_wav(pcm: bytes, sample_rate: int = DEFAULT_RATE, channels: int = 1) -> bytes:
    if not pcm:
        raise ValueError("Nema audio podataka.")
    if channels != 1:
        raise ValueError("Podržan je samo mono audio.")

    payload = pcm[: len(pcm) - (len(pcm) % 2)]
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(int(sample_rate))
        handle.writeframes(payload)
    return buffer.getvalue()


def wav_info(wav_bytes: bytes) -> dict:
    with wave.open(io.BytesIO(wav_bytes), "rb") as handle:
        return {
            "channels": handle.getnchannels(),
            "rate": handle.getframerate(),
            "frames": handle.getnframes(),
            "duration_ms": int(handle.getnframes() / handle.getframerate() * 1000),
        }

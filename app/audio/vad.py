# c:\Kortik\Kortik-Listener-App\app\audio\vad.py
"""
VAD (voice activity detection) + snimanje izgovora — cista Python logika.

Namera: ovo je mozak koji odlucuje "kada je korisnik poceo i zavrsio recenicu".
Ne zna nista o mikrofonu ni o KWS-u, pa se moze testirati bez zvucne kartice.

Ulaz:  20 ms chunkovi PCM-a (16 kHz, 16-bit mono, 640 bajtova)
Izlaz: `feed()` vraca bytes gotovog izgovora kada se detektuje kraj, inace None.
"""
from __future__ import annotations

import math
from array import array
from collections import deque
from dataclasses import dataclass
from typing import Deque, List, Optional

SAMPLE_RATE = 16000
CHUNK_MS = 20
CHUNK_SAMPLES = SAMPLE_RATE * CHUNK_MS // 1000
CHUNK_BYTES = CHUNK_SAMPLES * 2


def rms(pcm: bytes) -> float:
    """RMS amplitude int16 PCM-a (bez numpy)."""
    if not pcm:
        return 0.0
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return 0.0
    total = 0
    for value in samples:
        total += int(value) * int(value)
    return math.sqrt(total / len(samples))


def is_silence(pcm: bytes) -> bool:
    return rms(pcm) < 5.0


@dataclass
class VadConfig:
    speech_rms: float = 350.0        # apsolutni prag (tisina u sobi je ~20-80)
    silence_ms: int = 700            # koliko tišine = kraj rečenice
    min_speech_ms: int = 250         # kraće od ovoga = šum, odbacuje se
    pre_roll_ms: int = 300           # hvata početak reči pre detekcije
    max_utterance_ms: int = 6000     # hard cap da ne snimamo zauvek
    adaptive_factor: float = 2.5     # prag = max(speech_rms, ambient * factor)

    @property
    def silence_chunks(self) -> int:
        return max(1, self.silence_ms // CHUNK_MS)

    @property
    def min_speech_chunks(self) -> int:
        return max(1, self.min_speech_ms // CHUNK_MS)

    @property
    def pre_roll_chunks(self) -> int:
        return max(0, self.pre_roll_ms // CHUNK_MS)

    @property
    def max_chunks(self) -> int:
        return max(1, self.max_utterance_ms // CHUNK_MS)


class UtteranceRecorder:
    """Drzavna masina: IDLE -> RECORDING -> (vrati utterance) -> IDLE."""

    IDLE = "idle"
    RECORDING = "recording"

    def __init__(self, config: Optional[VadConfig] = None):
        self.config = config or VadConfig()
        self.state = self.IDLE
        self.ambient_rms: float = 20.0
        self._pre_roll: Deque[bytes] = deque(maxlen=max(1, self.config.pre_roll_chunks))
        self._buffer: List[bytes] = []
        self._silence_run = 0
        self._chunks_in_utterance = 0
        self._speech_chunks = 0
        self.last_rms: float = 0.0

    # ── pomocno ─────────────────────────────────────────────────────────────
    @property
    def is_recording(self) -> bool:
        return self.state == self.RECORDING

    def threshold(self) -> float:
        adaptive = self.ambient_rms * self.config.adaptive_factor
        return max(float(self.config.speech_rms), adaptive)

    def reset(self) -> None:
        self.state = self.IDLE
        self._buffer.clear()
        self._silence_run = 0
        self._chunks_in_utterance = 0
        self._speech_chunks = 0
        self._pre_roll.clear()

    def _start(self) -> None:
        self.state = self.RECORDING
        self._buffer = list(self._pre_roll)
        self._silence_run = 0
        self._chunks_in_utterance = 0
        self._speech_chunks = 0

    # ── glavni ulaz ─────────────────────────────────────────────────────────
    def feed(self, chunk: bytes) -> Optional[bytes]:
        if not chunk:
            return None

        level = rms(chunk)
        self.last_rms = level
        threshold = self.threshold()
        speech = level >= threshold

        if self.state == self.IDLE:
            # adaptivna procena suma (samo dok ne snimamo)
            self.ambient_rms = 0.95 * self.ambient_rms + 0.05 * min(level, 150.0)
            self._pre_roll.append(chunk)
            if speech:
                self._start()
                self._buffer.append(chunk)
                self._chunks_in_utterance = 1
            return None

        # RECORDING
        self._buffer.append(chunk)
        self._chunks_in_utterance += 1
        if speech:
            self._speech_chunks += 1
            self._silence_run = 0
        else:
            self._silence_run += 1

        done = False
        if self._silence_run >= self.config.silence_chunks:
            done = True
        elif self._chunks_in_utterance >= self.config.max_chunks:
            done = True

        if not done:
            return None

        audio = b"".join(self._buffer)

        # Zadrzi najvise `silence_ms` tisline na kraju (krace = brzi STT)
        if self._silence_run > self.config.silence_chunks:
            extra = (self._silence_run - self.config.silence_chunks) * CHUNK_BYTES
            if extra:
                audio = audio[:-extra]

        was_too_short = self._speech_chunks < self.config.min_speech_chunks
        self.reset()
        return None if was_too_short else audio

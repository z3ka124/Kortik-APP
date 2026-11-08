# -*- coding: utf-8 -*-
"""Testovi VAD-a i snimanja izgovora (bez zvucne kartice)."""
import sys
import unittest
from array import array
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.audio.vad import (  # noqa: E402
    CHUNK_BYTES,
    CHUNK_SAMPLES,
    UtteranceRecorder,
    VadConfig,
    is_silence,
    rms,
)


def chunk(value: int, samples: int = CHUNK_SAMPLES) -> bytes:
    return array("h", [value] * samples).tobytes()


SILENCE = chunk(0)
SPEECH = chunk(3000)


class RmsTests(unittest.TestCase):
    def test_silence(self):
        self.assertEqual(rms(SILENCE), 0.0)
        self.assertTrue(is_silence(SILENCE))

    def test_constant_signal(self):
        self.assertAlmostEqual(rms(chunk(1000)), 1000.0, delta=1.0)
        self.assertFalse(is_silence(chunk(1000)))

    def test_empty(self):
        self.assertEqual(rms(b""), 0.0)

    def test_odd_length(self):
        self.assertGreater(rms(chunk(500) + b"\x01"), 0.0)


class RecorderTests(unittest.TestCase):
    def _config(self, **overrides):
        base = dict(speech_rms=350.0, silence_ms=700, min_speech_ms=250, pre_roll_ms=300, max_utterance_ms=6000)
        base.update(overrides)
        return VadConfig(**base)

    def test_silence_only_produces_nothing(self):
        recorder = UtteranceRecorder(self._config())
        for _ in range(200):
            self.assertIsNone(recorder.feed(SILENCE))
        self.assertFalse(recorder.is_recording)

    def test_speech_then_silence_returns_utterance(self):
        recorder = UtteranceRecorder(self._config())
        for _ in range(20):
            recorder.feed(SPEECH)
        self.assertTrue(recorder.is_recording)

        result = None
        for _ in range(60):
            result = recorder.feed(SILENCE)
            if result:
                break

        self.assertIsNotNone(result)
        self.assertGreaterEqual(len(result), 20 * CHUNK_BYTES)
        self.assertFalse(recorder.is_recording)

    def test_pre_roll_is_included(self):
        config = self._config(pre_roll_ms=200)  # 10 chunkova
        recorder = UtteranceRecorder(config)

        for _ in range(10):
            recorder.feed(SILENCE)          # napuni pre-roll
        for _ in range(15):
            recorder.feed(SPEECH)           # 300 ms govora

        result = None
        for _ in range(60):
            result = recorder.feed(SILENCE)
            if result:
                break

        self.assertIsNotNone(result)
        # 10 pre-roll + 15 govora + najvise 35 tisline
        self.assertGreaterEqual(len(result), 25 * CHUNK_BYTES)

    def test_short_noise_is_discarded(self):
        recorder = UtteranceRecorder(self._config(min_speech_ms=250))
        recorder.feed(SPEECH)  # 20 ms "govora" (klik)
        result = None
        for _ in range(80):
            result = recorder.feed(SILENCE)
            if result is not None:
                break
        self.assertIsNone(result)
        self.assertFalse(recorder.is_recording)

    def test_hard_cap_returns_audio(self):
        config = self._config(max_utterance_ms=400)  # 20 chunkova
        recorder = UtteranceRecorder(config)
        result = None
        for _ in range(60):
            result = recorder.feed(SPEECH)
            if result is not None:
                break
        self.assertIsNotNone(result)
        self.assertFalse(recorder.is_recording)

    def test_ambient_adapts(self):
        recorder = UtteranceRecorder(self._config())
        before = recorder.ambient_rms
        for _ in range(100):
            recorder.feed(chunk(200))
        self.assertGreater(recorder.ambient_rms, before)

    def test_reset(self):
        recorder = UtteranceRecorder(self._config())
        for _ in range(20):
            recorder.feed(SPEECH)
        recorder.reset()
        self.assertFalse(recorder.is_recording)
        self.assertIsNone(recorder.feed(SILENCE))

    def test_empty_chunk_ignored(self):
        recorder = UtteranceRecorder(self._config())
        self.assertIsNone(recorder.feed(b""))


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Testovi za WAV pakovanje i cloud STT (bez mreze, sa laznim API-jem)."""
import asyncio
import sys
import unittest
from array import array
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.stt.base import create_stt  # noqa: E402
from app.stt.cloud import CloudSpeechToText  # noqa: E402
from app.stt.wav import pcm_to_wav, wav_info  # noqa: E402


def chunk(value: int, samples: int = 320) -> bytes:
    return array("h", [value] * samples).tobytes()


class WavTests(unittest.TestCase):
    def test_roundtrip_info(self):
        pcm = chunk(1000) * 50  # 50 * 20ms = 1s
        wav = pcm_to_wav(pcm)
        self.assertTrue(wav.startswith(b"RIFF"))
        info = wav_info(wav)
        self.assertEqual(info["channels"], 1)
        self.assertEqual(info["rate"], 16000)
        self.assertAlmostEqual(info["duration_ms"], 1000, delta=25)

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            pcm_to_wav(b"")

    def test_odd_length_truncated(self):
        wav = pcm_to_wav(chunk(500) + b"\x01")
        self.assertGreater(wav_info(wav)["frames"], 0)

    def test_stereo_rejected(self):
        with self.assertRaises(ValueError):
            pcm_to_wav(chunk(1), channels=2)


class FakeApi:
    def __init__(self, status="success", text="pusti senidah"):
        self.status = status
        self.text = text
        self.calls = []

    async def transcribe_audio(self, access_token, device_secret, wav_bytes, language="sr", model="whisper-large-v3-turbo"):
        self.calls.append(
            {
                "token": access_token,
                "secret": device_secret,
                "size": len(wav_bytes),
                "language": language,
                "model": model,
            }
        )
        return {"status": self.status, "text": self.text}


class CloudSttTests(unittest.TestCase):
    def _engine(self, api, language="sr"):
        async def credentials():
            return ("token-123", "secret-456")

        return CloudSpeechToText(api=api, credentials_provider=credentials, language=language)

    def test_sync_transcribe_is_rejected(self):
        engine = self._engine(FakeApi())
        with self.assertRaises(RuntimeError):
            engine.transcribe(chunk(100))

    def test_async_transcribe_success(self):
        api = FakeApi()
        engine = self._engine(api)
        text = asyncio.run(engine.transcribe_async(chunk(1000) * 40))
        self.assertEqual(text, "pusti senidah")
        self.assertEqual(len(api.calls), 1)
        self.assertEqual(api.calls[0]["token"], "token-123")
        self.assertEqual(api.calls[0]["secret"], "secret-456")
        self.assertEqual(api.calls[0]["model"], "whisper-large-v3-turbo")
        self.assertGreater(api.calls[0]["size"], 44)  # WAV header + audio

    def test_cloud_model_selection(self):
        api = FakeApi()

        async def credentials():
            return ("token-123", "secret-456")

        engine = CloudSpeechToText(
            api=api,
            credentials_provider=credentials,
            language="sr",
            model="whisper-large-v3",
        )
        asyncio.run(engine.transcribe_async(chunk(1000) * 20))
        self.assertEqual(api.calls[0]["model"], "whisper-large-v3")

    def test_async_transcribe_error_status_returns_empty(self):
        engine = self._engine(FakeApi(status="error", text="x"))
        self.assertEqual(asyncio.run(engine.transcribe_async(chunk(1000) * 20)), "")

    def test_async_transcribe_empty_audio(self):
        engine = self._engine(FakeApi())
        self.assertEqual(asyncio.run(engine.transcribe_async(b"")), "")

    def test_not_configured(self):
        engine = CloudSpeechToText(api=None, credentials_provider=None)
        self.assertFalse(engine.available())
        with self.assertRaises(RuntimeError):
            asyncio.run(engine.transcribe_async(chunk(100)))


class FactoryTests(unittest.TestCase):
    def test_cloud_without_session_falls_back(self):
        engine, note = create_stt("cloud", "sr", api=None, credentials_provider=None)
        self.assertTrue(note)
        # lokalni može biti None (nema faster-whisper) ili LocalWhisper
        if engine is not None:
            self.assertNotIsInstance(engine, CloudSpeechToText)

    def test_cloud_with_session(self):
        async def credentials():
            return ("t", "s")

        engine, note = create_stt("cloud", "sr", api=FakeApi(), credentials_provider=credentials)
        self.assertIsInstance(engine, CloudSpeechToText)
        self.assertEqual(note, "cloud")


if __name__ == "__main__":
    unittest.main()

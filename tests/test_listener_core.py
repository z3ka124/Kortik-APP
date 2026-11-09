# -*- coding: utf-8 -*-
"""Testovi orkestracije wake word -> snimak -> STT -> parser (bez uredjaja)."""
import sys
import unittest
from array import array
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.audio.vad import CHUNK_SAMPLES, UtteranceRecorder, VadConfig  # noqa: E402
from app.core.listener_core import ListenerCore  # noqa: E402


def chunk(value: int, samples: int = CHUNK_SAMPLES) -> bytes:
    return array("h", [value] * samples).tobytes()


SILENCE = chunk(0)
SPEECH = chunk(3000)


class FakeKws:
    def __init__(self, keyword: str = "HEY JARVIS"):
        self.keyword = keyword
        self.calls = 0
        self.resets = 0
        self.trigger_on_call = 1

    def process(self, pcm: bytes):
        self.calls += 1
        if self.calls == self.trigger_on_call:
            return self.keyword
        return None

    def reset(self):
        self.resets += 1


class FakeStt:
    def __init__(self, text: str = "pusti senidah bez tebe", fail: bool = False):
        self.text = text
        self.fail = fail
        self.calls = 0

    def transcribe(self, pcm: bytes, sample_rate: int = 16000) -> str:
        self.calls += 1
        if self.fail:
            raise RuntimeError("stt pukao")
        return self.text


class FakeClock:
    def __init__(self):
        self.value = 1000.0

    def __call__(self):
        return self.value


def make_core(keyword="HEY JARVIS", stt_text="pusti senidah bez tebe", clock=None, cooldown=1.2):
    kws = FakeKws(keyword)
    recorder = UtteranceRecorder(VadConfig(speech_rms=350, silence_ms=100, min_speech_ms=60, pre_roll_ms=40))
    stt = FakeStt(stt_text)
    core = ListenerCore(kws, recorder, stt, cooldown_seconds=cooldown, clock=clock or FakeClock())
    return core, kws, recorder, stt


class WakeAndRecordTests(unittest.TestCase):
    def test_no_wake_no_action(self):
        core, kws, _, _ = make_core()
        kws.trigger_on_call = 999
        for _ in range(50):
            self.assertIsNone(core.process_chunk(SILENCE))
        self.assertFalse(core.is_armed)

    def test_wake_then_utterance(self):
        core, _, _, _ = make_core()
        wake = core.process_chunk(SILENCE)
        self.assertIsNotNone(wake)
        self.assertEqual(wake.kind, "wake")
        self.assertEqual(wake.keyword, "HEY JARVIS")
        self.assertTrue(core.is_armed)

        # nakon wake word-a snimamo govor + tisinu -> dobijamo utterance
        for _ in range(6):
            core.process_chunk(SPEECH)

        utterance = None
        for _ in range(30):
            utterance = core.process_chunk(SILENCE)
            if utterance:
                break

        self.assertIsNotNone(utterance)
        self.assertEqual(utterance.kind, "utterance")
        self.assertGreater(len(utterance.audio), 5 * 640)
        self.assertFalse(core.is_armed)

    def test_cooldown_blocks_double_wake(self):
        clock = FakeClock()
        core, kws, _, _ = make_core(clock=clock, cooldown=5.0)
        kws.trigger_on_call = 1
        self.assertIsNotNone(core.process_chunk(SILENCE))
        core.reset()  # vrati se u IDLE, ali cooldown i dalje vazi
        clock.value += 1.0
        kws.trigger_on_call = 2
        self.assertIsNone(core.process_chunk(SILENCE))
        clock.value += 10.0
        self.assertIsNotNone(core.process_chunk(SILENCE))

    def test_empty_chunk(self):
        core, _, _, _ = make_core()
        self.assertIsNone(core.process_chunk(b""))


class UtteranceToCommandTests(unittest.TestCase):
    def test_play_command(self):
        core, _, _, stt = make_core(stt_text="pusti senidah bez tebe")
        action = core.process_utterance(SPEECH * 10)
        self.assertEqual(action.kind, "command")
        self.assertEqual(action.command, "play")
        self.assertEqual(action.query, "senidah bez tebe")
        self.assertEqual(stt.calls, 1)

    def test_wake_word_only(self):
        core, _, _, _ = make_core(stt_text="Hey Jarvis")
        action = core.process_utterance(SPEECH * 10)
        self.assertEqual(action.kind, "wake_only")

    def test_plain_text(self):
        core, _, _, _ = make_core(stt_text="kako si")
        action = core.process_utterance(SPEECH * 10)
        self.assertEqual(action.kind, "text")

    def test_stt_failure_is_swallowed(self):
        core, _, _, stt = make_core(stt_text="x")
        stt.fail = True
        self.assertIsNone(core.process_utterance(SPEECH * 10))

    def test_no_stt_returns_none(self):
        kws = FakeKws()
        recorder = UtteranceRecorder(VadConfig())
        core = ListenerCore(kws, recorder, None)
        self.assertIsNone(core.process_utterance(SPEECH))

    def test_empty_audio(self):
        core, _, _, _ = make_core()
        self.assertIsNone(core.process_utterance(b""))

    def test_parse_text_direct(self):
        core, _, _, _ = make_core()
        self.assertEqual(core.parse_text("skip").kind, "command")
        self.assertEqual(core.parse_text("skip").command, "skip")
        self.assertEqual(core.parse_text("Hej Jarvis").kind, "wake_only")
        self.assertIsNone(core.parse_text(""))


if __name__ == "__main__":
    unittest.main()

# -*- coding: utf-8 -*-
"""Wake word preko STT-a (Whisper) — „Hey Jarvis pusti X“ u jednom izgovoru."""
import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.audio.vad import UtteranceRecorder, VadConfig  # noqa: E402
from app.core.listener_core import ListenerCore  # noqa: E402


class FakeStt:
    def __init__(self, text: str):
        self.text = text

    def transcribe(self, pcm, sample_rate: int = 16000) -> str:
        return self.text


def make_core(text: str = "") -> ListenerCore:
    return ListenerCore(
        None,
        UtteranceRecorder(VadConfig()),
        FakeStt(text),
        wake_by_stt=True,
    )


class WakeBySttTests(unittest.TestCase):
    def test_full_command_in_one_utterance(self):
        core = make_core("Hey Jarvis pusti senidah bez tebe")
        action = core.process_utterance(b"\x00" * 640)
        self.assertIsNotNone(action)
        self.assertEqual(action.kind, "command")
        self.assertEqual(action.command, "play")
        self.assertEqual(action.query, "senidah bez tebe")

    def test_hej_jarvis_variant(self):
        core = make_core("Hej Jarvis pusti vidi je")
        action = core.process_utterance(b"\x00" * 640)
        self.assertEqual(action.kind, "command")
        self.assertEqual(action.query, "vidi je")

    def test_wake_word_only_then_followup(self):
        core = make_core("Hey Jarvis")
        first = core.process_utterance(b"\x00" * 640)
        self.assertEqual(first.kind, "wake_only")

        second = core.parse_text("pusti senidah")
        self.assertIsNotNone(second)
        self.assertEqual(second.kind, "command")
        self.assertEqual(second.command, "play")

    def test_no_wake_word_is_ignored(self):
        core = make_core("pusti senidah bez tebe")
        self.assertIsNone(core.process_utterance(b"\x00" * 640))

    def test_wake_word_with_non_command_text(self):
        core = make_core("Hey Jarvis kako si")
        action = core.process_utterance(b"\x00" * 640)
        self.assertEqual(action.kind, "text")

    def test_wake_word_mid_sentence_not_matched(self):
        core = make_core("ja sam rekao hey jarvis juce")
        self.assertIsNone(core.process_utterance(b"\x00" * 640))

    def test_kortik_is_not_a_wake_word(self):
        core = make_core("Kortik pusti senidah bez tebe")
        self.assertIsNone(core.process_utterance(b"\x00" * 640))

    def test_oww_mode_still_works(self):
        core = ListenerCore(None, UtteranceRecorder(VadConfig()), FakeStt("pusti senidah"))
        action = core.process_utterance(b"\x00" * 640)
        self.assertEqual(action.kind, "command")
        self.assertEqual(action.query, "senidah")


if __name__ == "__main__":
    unittest.main()

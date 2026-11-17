# -*- coding: utf-8 -*-
"""Parser komandi — wake word je „Hey Kortik“; razume srpske i engleske komande."""
import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.core.parser import (  # noqa: E402
    is_wake_word_only,
    normalize,
    parse_command,
    strip_wake_word,
)


class NormalizeTests(unittest.TestCase):
    def test_diacritics_and_case(self):
        self.assertEqual(
            normalize("Hey Kortik  PUSTI  Senidah, bez tebe!"),
            "hey kortik pusti senidah bez tebe",
        )

    def test_empty(self):
        self.assertEqual(normalize(""), "")
        self.assertEqual(normalize(None), "")


class WakeWordTests(unittest.TestCase):
    def test_strip_variants(self):
        for phrase in ("Hey Kortik pusti x", "hey kortik pusti x", "HEJ KORTIK pusti x", "kortik pusti x"):
            remainder, had = strip_wake_word(phrase)
            self.assertTrue(had, phrase)
            self.assertEqual(remainder, "pusti x")

    def test_wake_word_only(self):
        self.assertTrue(is_wake_word_only("Hey Kortik"))
        self.assertTrue(is_wake_word_only("kortik"))
        self.assertFalse(is_wake_word_only("Hey Kortik pusti x"))
        self.assertFalse(is_wake_word_only("kako si"))

    def test_jarvis_is_no_longer_a_wake_word(self):
        for phrase in ("jarvis pusti x", "Jarvis pusti x", "hey jarvis pusti x", "jarvis"):
            _, had = strip_wake_word(phrase)
            self.assertFalse(had, phrase)


class ParseCommandTests(unittest.TestCase):
    def test_play_serbian(self):
        self.assertEqual(parse_command("Hey Kortik pusti Senidah bez tebe"), ("play", "senidah bez tebe"))

    def test_play_english(self):
        self.assertEqual(parse_command("Hey Kortik play vidi je"), ("play", "vidi je"))

    def test_play_without_wake_word(self):
        self.assertEqual(parse_command("pusti senidah"), ("play", "senidah"))

    def test_play_implicit_song_name(self):
        self.assertEqual(parse_command("Hey Kortik senidah bez tebe"), ("play", "senidah bez tebe"))

    def test_skip(self):
        for phrase in ("Hey Kortik skip", "Hey Kortik preskoči", "Hey Kortik dalje", "Hey Kortik sledeća"):
            self.assertEqual(parse_command(phrase), ("skip", ""), phrase)

    def test_stop(self):
        for phrase in ("Hey Kortik stop", "Hey Kortik stani", "Hey Kortik ugasi", "Hey Kortik prekini"):
            self.assertEqual(parse_command(phrase), ("stop", ""), phrase)

    def test_pause_and_resume(self):
        self.assertEqual(parse_command("Hey Kortik pauza"), ("pause", ""))
        self.assertEqual(parse_command("Hey Kortik pauziraj"), ("pause", ""))
        self.assertEqual(parse_command("Hey Kortik nastavi"), ("resume", ""))
        self.assertEqual(parse_command("Hey Kortik pusti dalje"), ("resume", ""))

    def test_volume_absolute(self):
        self.assertEqual(parse_command("Hey Kortik glasnoća 80"), ("volume", "80"))
        self.assertEqual(parse_command("Hey Kortik volume 55"), ("volume", "55"))
        self.assertEqual(parse_command("Hey Kortik volume fifty"), ("volume", "50"))
        self.assertEqual(parse_command("Hey Kortik volume 200"), ("volume", "200"))

    def test_volume_out_of_range_rejected(self):
        self.assertIsNone(parse_command("Hey Kortik volume 0"))
        self.assertIsNone(parse_command("Hey Kortik glasnoća 201"))

    def test_volume_relative(self):
        self.assertEqual(parse_command("Hey Kortik pojačaj"), ("volume", "+15"))
        self.assertEqual(parse_command("Hey Kortik smanji"), ("volume", "-15"))
        self.assertEqual(parse_command("Hey Kortik utišaj"), ("volume", "-15"))

    def test_not_a_command(self):
        self.assertIsNone(parse_command("kako si"))
        self.assertIsNone(parse_command("Hey Kortik"))
        self.assertIsNone(parse_command(""))
        self.assertIsNone(parse_command("Hey Kortik pusti"))
        # „jarvis" više nije wake word
        self.assertIsNone(parse_command("jarvis pusti senidah"))

    def test_fillers_are_removed(self):
        self.assertEqual(parse_command("Hey Kortik pusti mi molim te senidah"), ("play", "senidah"))


class AutoplayCommandTests(unittest.TestCase):
    def test_autoplay_on(self):
        for phrase in ("Hey Kortik autoplay on", "Hey Kortik auto play on", "Hey Kortik autoplej on"):
            self.assertEqual(parse_command(phrase), ("autoplay", "on"), phrase)

    def test_autoplay_off(self):
        for phrase in ("Hey Kortik autoplay off", "Hey Kortik autoplej off"):
            self.assertEqual(parse_command(phrase), ("autoplay", "off"), phrase)

    def test_autoplay_serbian(self):
        self.assertEqual(parse_command("Hey Kortik uključi autoplay"), ("autoplay", "on"))
        self.assertEqual(parse_command("Hey Kortik isključi autoplay"), ("autoplay", "off"))
        self.assertEqual(parse_command("Hey Kortik ugasi autoplay"), ("autoplay", "off"))

    def test_autoplay_without_mode_requires_explicit(self):
        # samo "autoplay" bez on/off = nije komanda (zahteva eksplicitno)
        self.assertIsNone(parse_command("Hey Kortik autoplay"))


class JumpCommandTests(unittest.TestCase):
    def test_jump_numeric(self):
        self.assertEqual(parse_command("Hey Kortik jump 3"), ("jump", "3"))
        self.assertEqual(parse_command("Hey Kortik skoci na 2"), ("jump", "2"))
        self.assertEqual(parse_command("Hey Kortik prebaci na 5"), ("jump", "5"))
        self.assertEqual(parse_command("Hey Kortik idi na 4"), ("jump", "4"))

    def test_jump_word_numbers(self):
        self.assertEqual(parse_command("Hey Kortik pesma tri"), ("jump", "3"))
        self.assertEqual(parse_command("Hey Kortik skoci na jedan"), ("jump", "1"))
        self.assertEqual(parse_command("Hey Kortik jump two"), ("jump", "2"))


class DisconnectCommandTests(unittest.TestCase):
    def test_disconnect_variants(self):
        for phrase in ("Hey Kortik disconnect", "Hey Kortik izadji", "Hey Kortik napusti", "Hey Kortik leave"):
            self.assertEqual(parse_command(phrase), ("disconnect", ""), phrase)


class ModerationVoiceCommandTests(unittest.TestCase):
    def test_mute_preserves_target_casing(self):
        self.assertEqual(parse_command("Hey Kortik mute Marko_VIP"), ("mute", "Marko_VIP"))
        self.assertEqual(parse_command("Hey Kortik mutiraj Stefan"), ("mute", "Stefan"))
        self.assertEqual(parse_command("Hey Kortik utisi DJ_Alex"), ("mute", "DJ_Alex"))

    def test_deafen_preserves_target_casing(self):
        self.assertEqual(parse_command("Hey Kortik deafen Nikola"), ("deafen", "Nikola"))
        self.assertEqual(parse_command("Hey Kortik ogluvi Petar"), ("deafen", "Petar"))

    def test_mute_without_target_is_rejected(self):
        self.assertIsNone(parse_command("Hey Kortik mute"))
        self.assertIsNone(parse_command("Hey Kortik mutiraj"))


if __name__ == "__main__":
    unittest.main()
# -*- coding: utf-8 -*-
"""Parser komandi — wake word je „Hey Jarvis"; razume srpske i engleske komande."""
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
            normalize("Hey Jarvis  PUSTI  Senidah, bez tebe!"),
            "hey jarvis pusti senidah bez tebe",
        )

    def test_empty(self):
        self.assertEqual(normalize(""), "")
        self.assertEqual(normalize(None), "")


class WakeWordTests(unittest.TestCase):
    def test_strip_variants(self):
        for phrase in ("Hey Jarvis pusti x", "hey jarvis pusti x", "HEJ JARVIS pusti x", "jarvis pusti x"):
            remainder, had = strip_wake_word(phrase)
            self.assertTrue(had, phrase)
            self.assertEqual(remainder, "pusti x")

    def test_wake_word_only(self):
        self.assertTrue(is_wake_word_only("Hey Jarvis"))
        self.assertTrue(is_wake_word_only("jarvis"))
        self.assertFalse(is_wake_word_only("Hey Jarvis pusti x"))
        self.assertFalse(is_wake_word_only("kako si"))

    def test_kortik_is_no_longer_a_wake_word(self):
        for phrase in ("kortik pusti x", "Kortik pusti x", "hej kortik pusti x", "Kortik"):
            _, had = strip_wake_word(phrase)
            self.assertFalse(had, phrase)


class ParseCommandTests(unittest.TestCase):
    def test_play_serbian(self):
        self.assertEqual(parse_command("Hey Jarvis pusti Senidah bez tebe"), ("play", "senidah bez tebe"))

    def test_play_english(self):
        self.assertEqual(parse_command("Hey Jarvis play vidi je"), ("play", "vidi je"))

    def test_play_without_wake_word(self):
        self.assertEqual(parse_command("pusti senidah"), ("play", "senidah"))

    def test_play_implicit_song_name(self):
        self.assertEqual(parse_command("Hey Jarvis senidah bez tebe"), ("play", "senidah bez tebe"))

    def test_skip(self):
        for phrase in ("Hey Jarvis skip", "Hey Jarvis preskoči", "Hey Jarvis dalje", "Hey Jarvis sledeća"):
            self.assertEqual(parse_command(phrase), ("skip", ""), phrase)

    def test_stop(self):
        for phrase in ("Hey Jarvis stop", "Hey Jarvis stani", "Hey Jarvis ugasi", "Hey Jarvis prekini"):
            self.assertEqual(parse_command(phrase), ("stop", ""), phrase)

    def test_pause_and_resume(self):
        self.assertEqual(parse_command("Hey Jarvis pauza"), ("pause", ""))
        self.assertEqual(parse_command("Hey Jarvis pauziraj"), ("pause", ""))
        self.assertEqual(parse_command("Hey Jarvis nastavi"), ("resume", ""))
        self.assertEqual(parse_command("Hey Jarvis pusti dalje"), ("resume", ""))

    def test_volume_absolute(self):
        self.assertEqual(parse_command("Hey Jarvis glasnoća 80"), ("volume", "80"))
        self.assertEqual(parse_command("Hey Jarvis volume 55"), ("volume", "55"))
        self.assertEqual(parse_command("Hey Jarvis volume fifty"), ("volume", "50"))
        self.assertEqual(parse_command("Hey Jarvis volume 200"), ("volume", "200"))

    def test_volume_out_of_range_rejected(self):
        self.assertIsNone(parse_command("Hey Jarvis volume 0"))
        self.assertIsNone(parse_command("Hey Jarvis glasnoća 201"))

    def test_volume_relative(self):
        self.assertEqual(parse_command("Hey Jarvis pojačaj"), ("volume", "+15"))
        self.assertEqual(parse_command("Hey Jarvis smanji"), ("volume", "-15"))
        self.assertEqual(parse_command("Hey Jarvis utišaj"), ("volume", "-15"))

    def test_not_a_command(self):
        self.assertIsNone(parse_command("kako si"))
        self.assertIsNone(parse_command("Hey Jarvis"))
        self.assertIsNone(parse_command(""))
        self.assertIsNone(parse_command("Hey Jarvis pusti"))
        # „kortik" više nije wake word
        self.assertIsNone(parse_command("kortik pusti senidah"))

    def test_fillers_are_removed(self):
        self.assertEqual(parse_command("Hey Jarvis pusti mi molim te senidah"), ("play", "senidah"))


class AutoplayCommandTests(unittest.TestCase):
    def test_autoplay_on(self):
        for phrase in ("Hey Jarvis autoplay on", "Hey Jarvis auto play on", "Hey Jarvis autoplej on"):
            self.assertEqual(parse_command(phrase), ("autoplay", "on"), phrase)

    def test_autoplay_off(self):
        for phrase in ("Hey Jarvis autoplay off", "Hey Jarvis autoplej off"):
            self.assertEqual(parse_command(phrase), ("autoplay", "off"), phrase)

    def test_autoplay_serbian(self):
        self.assertEqual(parse_command("Hey Jarvis uključi autoplay"), ("autoplay", "on"))
        self.assertEqual(parse_command("Hey Jarvis isključi autoplay"), ("autoplay", "off"))
        self.assertEqual(parse_command("Hey Jarvis ugasi autoplay"), ("autoplay", "off"))

    def test_autoplay_without_mode_requires_explicit(self):
        # samo "autoplay" bez on/off = nije komanda (zahteva eksplicitno)
        self.assertIsNone(parse_command("Hey Jarvis autoplay"))


class JumpCommandTests(unittest.TestCase):
    def test_jump_numeric(self):
        self.assertEqual(parse_command("Hey Jarvis jump 3"), ("jump", "3"))
        self.assertEqual(parse_command("Hey Jarvis skoci na 2"), ("jump", "2"))
        self.assertEqual(parse_command("Hey Jarvis prebaci na 5"), ("jump", "5"))
        self.assertEqual(parse_command("Hey Jarvis idi na 4"), ("jump", "4"))

    def test_jump_word_numbers(self):
        self.assertEqual(parse_command("Hey Jarvis pesma tri"), ("jump", "3"))
        self.assertEqual(parse_command("Hey Jarvis skoci na jedan"), ("jump", "1"))
        self.assertEqual(parse_command("Hey Jarvis jump two"), ("jump", "2"))


class DisconnectCommandTests(unittest.TestCase):
    def test_disconnect_variants(self):
        for phrase in ("Hey Jarvis disconnect", "Hey Jarvis izadji", "Hey Jarvis napusti", "Hey Jarvis leave"):
            self.assertEqual(parse_command(phrase), ("disconnect", ""), phrase)


class ModerationVoiceCommandTests(unittest.TestCase):
    def test_mute_preserves_target_casing(self):
        self.assertEqual(parse_command("Hey Jarvis mute Marko_VIP"), ("mute", "Marko_VIP"))
        self.assertEqual(parse_command("Hey Jarvis mutiraj Stefan"), ("mute", "Stefan"))
        self.assertEqual(parse_command("Hey Jarvis utisi DJ_Alex"), ("mute", "DJ_Alex"))

    def test_deafen_preserves_target_casing(self):
        self.assertEqual(parse_command("Hey Jarvis deafen Nikola"), ("deafen", "Nikola"))
        self.assertEqual(parse_command("Hey Jarvis ogluvi Petar"), ("deafen", "Petar"))

    def test_mute_without_target_is_rejected(self):
        self.assertIsNone(parse_command("Hey Jarvis mute"))
        self.assertIsNone(parse_command("Hey Jarvis mutiraj"))



if __name__ == "__main__":
    unittest.main()

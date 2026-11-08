# -*- coding: utf-8 -*-
"""Parser komandi — mora da razume i srpske i engleske varijante."""
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
        self.assertEqual(normalize("Kortik  PUSTI  Senidah, bez tebe!"), "kortik pusti senidah bez tebe")

    def test_empty(self):
        self.assertEqual(normalize(""), "")
        self.assertEqual(normalize(None), "")


class WakeWordTests(unittest.TestCase):
    def test_strip_variants(self):
        for phrase in ("Kortik pusti x", "kortik pusti x", "HEJ KORTIK pusti x", "Hej Kortik pusti x"):
            remainder, had = strip_wake_word(phrase)
            self.assertTrue(had, phrase)
            self.assertEqual(remainder, "pusti x")

    def test_wake_word_only(self):
        self.assertTrue(is_wake_word_only("Kortik"))
        self.assertTrue(is_wake_word_only("Hej Kortik"))
        self.assertFalse(is_wake_word_only("Kortik pusti x"))
        self.assertFalse(is_wake_word_only("kako si"))


class ParseCommandTests(unittest.TestCase):
    def test_play_serbian(self):
        self.assertEqual(parse_command("Kortik pusti Senidah bez tebe"), ("play", "senidah bez tebe"))

    def test_play_english(self):
        self.assertEqual(parse_command("Kortik play vidi je"), ("play", "vidi je"))

    def test_play_without_wake_word(self):
        self.assertEqual(parse_command("pusti senidah"), ("play", "senidah"))

    def test_play_implicit_song_name(self):
        self.assertEqual(parse_command("Kortik senidah bez tebe"), ("play", "senidah bez tebe"))

    def test_skip(self):
        for phrase in ("Kortik skip", "Kortik preskoči", "Kortik dalje", "Kortik sledeća"):
            self.assertEqual(parse_command(phrase), ("skip", ""), phrase)

    def test_stop(self):
        for phrase in ("Kortik stop", "Kortik stani", "Kortik ugasi", "Kortik prekini"):
            self.assertEqual(parse_command(phrase), ("stop", ""), phrase)

    def test_pause_and_resume(self):
        self.assertEqual(parse_command("Kortik pauza"), ("pause", ""))
        self.assertEqual(parse_command("Kortik pauziraj"), ("pause", ""))
        self.assertEqual(parse_command("Kortik nastavi"), ("resume", ""))
        self.assertEqual(parse_command("Kortik pusti dalje"), ("resume", ""))

    def test_volume_absolute(self):
        self.assertEqual(parse_command("Kortik glasnoća 80"), ("volume", "80"))
        self.assertEqual(parse_command("Kortik volume 55"), ("volume", "55"))
        self.assertEqual(parse_command("Kortik volume fifty"), ("volume", "50"))

    def test_volume_relative(self):
        self.assertEqual(parse_command("Kortik pojačaj"), ("volume", "+15"))
        self.assertEqual(parse_command("Kortik smanji"), ("volume", "-15"))
        self.assertEqual(parse_command("Kortik utišaj"), ("volume", "-15"))

    def test_not_a_command(self):
        self.assertIsNone(parse_command("kako si"))
        self.assertIsNone(parse_command("Kortik"))
        self.assertIsNone(parse_command(""))
        self.assertIsNone(parse_command("Kortik pusti"))

    def test_fillers_are_removed(self):
        self.assertEqual(parse_command("Kortik pusti mi molim te senidah"), ("play", "senidah"))


if __name__ == "__main__":
    unittest.main()

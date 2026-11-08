# -*- coding: utf-8 -*-
"""
Guard testovi za wake word konfiguraciju.

Regresija koju cuvamo: `models/sherpa-kws/keywords.txt` u repou ima prag
`#0.08` (preosetljivo -> lažni pozivi na običan razgovor) i sadrži jarvis/alexa.
Aplikacija zato koristi sopstveni `keywords_kortik.txt` sa pragom >= 0.25.
"""
import re
import sys
import unittest
from array import array
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.kws.sherpa_kws import (  # noqa: E402
    SherpaKws,
    default_keywords_file,
    default_model_dir,
    pcm16_to_float,
    threshold_from_sensitivity,
)

LINE_RE = re.compile(r"^(?:▁\S.*|\S.*)\s:\s*[\d.]+\s+#\s*[\d.]+$")


def _keyword_lines():
    path = default_keywords_file()
    return [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


class KeywordsFileTests(unittest.TestCase):
    def test_file_exists_and_is_bundled(self):
        path = default_keywords_file()
        self.assertTrue(path.exists(), path)
        self.assertEqual(path.name, "keywords_kortik.txt")

    def test_contains_kortik_variants(self):
        joined = " ".join(_keyword_lines())
        self.assertIn("K OR TI K", joined)
        self.assertIn("HE Y", joined)

    def test_no_foreign_wake_words(self):
        joined = " ".join(_keyword_lines()).upper()
        self.assertNotIn("JARVIS", joined)
        self.assertNotIn("ALEXA", joined)

    def test_all_lines_have_score_and_threshold(self):
        for line in _keyword_lines():
            self.assertRegex(line, r":\s*[\d.]+\s*#\s*[\d.]+$", f"loš format: {line}")

    def test_thresholds_are_not_dangerously_low(self):
        for line in _keyword_lines():
            threshold = float(line.rsplit("#", 1)[1])
            self.assertGreaterEqual(threshold, 0.15, f"preosetljiv prag u: {line}")

    def test_len_no_junk(self):
        self.assertLessEqual(len(_keyword_lines()), 12)
        self.assertGreaterEqual(len(_keyword_lines()), 1)


class ThresholdMappingTests(unittest.TestCase):
    def test_range(self):
        self.assertAlmostEqual(threshold_from_sensitivity(0.0), 0.45, places=3)
        self.assertAlmostEqual(threshold_from_sensitivity(1.0), 0.10, places=3)

    def test_monotonic(self):
        values = [threshold_from_sensitivity(s / 10) for s in range(11)]
        for lower, higher in zip(values, values[1:]):
            self.assertGreaterEqual(lower, higher)

    def test_clamps(self):
        self.assertEqual(threshold_from_sensitivity(-5), threshold_from_sensitivity(0.0))
        self.assertEqual(threshold_from_sensitivity(5), threshold_from_sensitivity(1.0))


class PcmConversionTests(unittest.TestCase):
    def test_length_and_range(self):
        pcm = array("h", [0, 16384, -32768, 32767]).tobytes()
        values = pcm16_to_float(pcm)
        self.assertEqual(len(values), 4)
        self.assertAlmostEqual(values[1], 0.5, places=2)
        self.assertLessEqual(max(values), 1.0)
        self.assertGreaterEqual(min(values), -1.0)

    def test_empty(self):
        self.assertEqual(pcm16_to_float(b""), [])


class AvailabilityTests(unittest.TestCase):
    def test_available_returns_bool(self):
        self.assertIsInstance(SherpaKws.available(), bool)

    def test_model_dir_contains_tokens(self):
        model_dir = default_model_dir()
        if not (model_dir / "tokens.txt").exists():
            self.skipTest("model nije prisutan u okruženju")
        self.assertTrue(SherpaKws.available(model_dir))


if __name__ == "__main__":
    unittest.main()

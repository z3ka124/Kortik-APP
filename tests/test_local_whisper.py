# -*- coding: utf-8 -*-
"""
Regresioni test: lokalni STT (faster-whisper) MORA da dobije np.ndarray.

Root cause (v1.1.0): `pcm16_to_float` je vracao Python listu -> faster-whisper
je listu tretirao kao fajl i pozivao PyAV (`av.open(..., metadata_errors=...)`)
-> STT uvek vratio prazan tekst -> nijedna glasovna komanda nije radila.
"""
import sys
import unittest
from array import array
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

import numpy as np  # noqa: E402

from app.stt.local_whisper import pcm16_to_float  # noqa: E402


class PcmConversionTests(unittest.TestCase):
    def test_returns_numpy_ndarray(self):
        pcm = array("h", [0, 16384, -32768, 32767]).tobytes()
        result = pcm16_to_float(pcm)
        self.assertIsInstance(result, np.ndarray)

    def test_returns_float32(self):
        result = pcm16_to_float(array("h", [16384]).tobytes())
        self.assertEqual(result.dtype, np.float32)

    def test_values_in_range(self):
        result = pcm16_to_float(array("h", [16384, -32768, 32767]).tobytes())
        self.assertLessEqual(float(result.max()), 1.0)
        self.assertGreaterEqual(float(result.min()), -1.0)

    def test_odd_length_truncated(self):
        result = pcm16_to_float(b"\x01\x02\x03")  # 3 bajta = 1.5 samplea
        self.assertIsInstance(result, np.ndarray)
        self.assertEqual(result.size, 1)

    def test_not_a_list(self):
        result = pcm16_to_float(array("h", [1, 2]).tobytes())
        self.assertNotIsInstance(result, list)


if __name__ == "__main__":
    unittest.main()
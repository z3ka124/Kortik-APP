# -*- coding: utf-8 -*-
"""OpenWakeWord (hey_jarvis) konfiguracija i ponasanje — guard testovi."""
import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.kws.openwakeword_kws import (  # noqa: E402
    FRAME_BYTES,
    FRAME_SAMPLES,
    OpenWakeWordKws,
    default_model_dir,
    threshold_from_sensitivity,
)


class ThresholdMappingTests(unittest.TestCase):
    def test_range(self):
        self.assertAlmostEqual(threshold_from_sensitivity(0.0), 0.75, places=3)
        self.assertAlmostEqual(threshold_from_sensitivity(1.0), 0.30, places=3)

    def test_monotonic(self):
        values = [threshold_from_sensitivity(s / 10) for s in range(11)]
        for lower, higher in zip(values, values[1:]):
            self.assertGreaterEqual(lower, higher)

    def test_clamps(self):
        self.assertEqual(threshold_from_sensitivity(-5), threshold_from_sensitivity(0.0))
        self.assertEqual(threshold_from_sensitivity(5), threshold_from_sensitivity(1.0))


class FrameSizeTests(unittest.TestCase):
    def test_frame_is_80ms(self):
        self.assertEqual(FRAME_SAMPLES, 1280)
        self.assertEqual(FRAME_BYTES, 1280 * 2)


class ModelDirTests(unittest.TestCase):
    def test_dir_contains_models(self):
        model_dir = default_model_dir()
        if not (model_dir / "hey_jarvis_v0.1.onnx").exists():
            self.skipTest("OWW model nije prisutan u okruženju")
        self.assertTrue(OpenWakeWordKws.available(model_dir))


class AvailabilityTests(unittest.TestCase):
    def test_available_returns_bool(self):
        self.assertIsInstance(OpenWakeWordKws.available(), bool)


class DetectionTests(unittest.TestCase):
    def test_silence_does_not_trigger(self):
        if not OpenWakeWordKws.available():
            self.skipTest("onnxruntime/openwakeword nije instaliran")
        kws = OpenWakeWordKws()
        kws.load()
        silence = b"\x00\x00" * 16000  # 1 s čiste tišine
        self.assertIsNone(kws.process(silence))
        self.assertLessEqual(kws.peak_score(silence), 0.3)


if __name__ == "__main__":
    unittest.main()
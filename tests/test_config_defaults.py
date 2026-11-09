# -*- coding: utf-8 -*-
"""Config defaulti — STT model lokalno/cloud + wake word uvek akusticni."""
import sys
import unittest
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.config import Settings  # noqa: E402


class ConfigDefaultTests(unittest.TestCase):
    def test_stt_model_size_default_small(self):
        self.assertEqual(Settings().stt_model_size, "small")

    def test_stt_cloud_model_default_turbo(self):
        self.assertEqual(Settings().stt_cloud_model, "whisper-large-v3-turbo")

    def test_stt_mode_default_local(self):
        self.assertEqual(Settings().stt_mode, "local")

    def test_from_dict_filters_unknown(self):
        s = Settings.from_dict({"stt_cloud_model": "whisper-large-v3", "nepostojece": 123})
        self.assertEqual(s.stt_cloud_model, "whisper-large-v3")
        self.assertTrue(not hasattr(s, "nepostojece"))


if __name__ == "__main__":
    unittest.main()
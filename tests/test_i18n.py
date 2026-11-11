# c:\Kortik\Kortik-Listener-App\tests\test_i18n.py
import unittest
from app.i18n import I18nManager, tr, SUPPORTED_LANGUAGES, TRANSLATIONS


class I18nTests(unittest.TestCase):
    def setUp(self):
        self.mgr = I18nManager(default_lang="sr")

    def test_default_serbian(self):
        self.assertEqual(self.mgr.current_language, "sr")
        self.assertEqual(self.mgr.tr("app_title"), "Kortik Listener")
        self.assertEqual(self.mgr.tr("bot_online"), "Bot: online")

    def test_switch_to_english(self):
        self.mgr.set_language("en")
        self.assertEqual(self.mgr.current_language, "en")
        self.assertEqual(self.mgr.tr("bot_online"), "Bot: Online")
        self.assertEqual(self.mgr.tr("pairing_box_title"), "Confirm code on dashboard")

    def test_formatting_parameters(self):
        self.mgr.set_language("sr")
        formatted_sr = self.mgr.tr("vc_in", channel="Muzika", guild="Balkan")
        self.assertIn("Muzika", formatted_sr)
        self.assertIn("Balkan", formatted_sr)

        self.mgr.set_language("en")
        formatted_en = self.mgr.tr("vc_in", channel="Music", guild="Global")
        self.assertIn("Music", formatted_en)
        self.assertIn("Global", formatted_en)

    def test_fallback_to_english_for_unknown_key(self):
        self.mgr.set_language("de")  # de will fallback to en
        self.assertEqual(self.mgr.tr("bot_online"), "Bot: Online")

    def test_missing_key_returns_default_or_key(self):
        self.assertEqual(self.mgr.tr("non_existent_key_xyz", default="Fallback"), "Fallback")
        self.assertEqual(self.mgr.tr("non_existent_key_xyz"), "non_existent_key_xyz")


if __name__ == "__main__":
    unittest.main()

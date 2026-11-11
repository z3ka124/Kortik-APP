# c:\Kortik\Kortik-Listener-App\app\i18n.py
"""
Lokalizacija (i18n) za Kortik Listener aplikaciju.
- Kompletni prevodi za srpski (sr) i engleski (en), sa fallback-om za ostale jezike.
- Dinamička promena jezika bez restarta aplikacije (Qt signal).
"""
from __future__ import annotations

from typing import Any, Dict, Optional

try:
    from PySide6.QtCore import QObject, Signal
except ImportError:
    class QObject:
        pass

    class _SignalStub:
        def __init__(self, *args: Any):
            self._callbacks = []

        def connect(self, cb: Any) -> None:
            self._callbacks.append(cb)

        def emit(self, *args: Any, **kwargs: Any) -> None:
            for cb in self._callbacks:
                try:
                    cb(*args, **kwargs)
                except Exception:
                    pass

    def Signal(*args: Any) -> Any:
        return _SignalStub(*args)

SUPPORTED_LANGUAGES: Dict[str, str] = {
    "sr": "Srpski",
    "en": "English",
    "de": "Deutsch",
    "fr": "Français",
    "es": "Español",
    "it": "Italiano",
    "ru": "Русский",
    "hr": "Hrvatski",
    "bs": "Bosanski",
    "sl": "Slovenščina",
    "mk": "Makedonski",
    "auto": "Auto (STT)",
}

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "sr": {
        # App
        "app_title": "Kortik Listener",
        "logged_in": "Ulogovan",
        "not_logged_in": "Nisi ulogovan",
        "discord_user": "Discord ID: {user_id}",
        "device_info": "Discord ID: {user_id} · uređaj {device_id}",

        # Pairing
        "pairing_box_title": "Potvrdi kod na dashboardu",
        "pair_device_btn": "Upari uređaj",
        "device_name_label": "Ime uređaja (kako se vidi na dashboardu)",
        "device_name_placeholder": "npr. Moj PC / Radni laptop",
        "pairing_start": "Započinjem uparivanje…",
        "pairing_waiting": "Čekam potvrdu na dashboardu… (kod važi 10 minuta)",
        "pairing_hint": "Klikni „Upari uređaj“ da dobiješ kod.",
        "pairing_success": "Uređaj je uspešno uparen.",
        "pairing_failed": "Uparivanje nije uspelo: {error}",
        "open_dashboard_btn": "Otvori dashboard",
        "unlink_device_btn": "Odjavi uređaj",
        "unlink_confirm_title": "Odjava uređaja",
        "unlink_confirm_msg": "Da li sigurno želiš da odjaviš ovaj uređaj sa svog Discord naloga?",
        "unlinked_msg": "Uređaj je odjavljen.",

        # Status
        "status_box_title": "Status",
        "bot_online": "Bot: online",
        "bot_offline": "Bot: offline",
        "vc_in": "VC: {channel}  (server {guild})",
        "vc_not_in": "VC: nisi u glasovnom kanalu",
        "busy_free": "Zauzetost: bot je slobodan",
        "busy_other_vc": "Zauzetost: bot svira u drugom kanalu",
        "plugin_active": "Plugin: uključen",
        "plugin_disabled": "Plugin: isključen na serveru",
        "plugin_unknown": "Plugin: nepoznato",
        "listening_active": "🎙️ Slušam — čekam „Hey Jarvis“",
        "listening_stopped": "⏸️ Slušanje je isključeno",
        "listening_not_in_vc": "⏸️ Slušanje isključeno · nisi u voice kanalu",
        "listening_ptt_active": "🎙️ PTT: snimam… pusti taster",
        "listening_ptt_off": "⏸️ PTT: snimanje isključeno",
        "heard_wake": "👂 Čuo sam „{keyword}“ — govori…",
        "wake_only": "👂 Samo wake word — čekam komandu.",

        # Listening controls
        "listen_wake_checkbox": "Slušam wake word „Hey Jarvis“",
        "listen_btn_start": "Uključi slušanje",
        "listen_btn_stop": "Zaustavi slušanje",
        "listen_mic_level_tooltip": "Nivo mikrofona dok slušam",

        # Test command
        "test_cmd_box": "Test komanda",
        "test_cmd_placeholder": 'npr. "pusti senidah bez tebe", "skip", "jump 2" ili "mute Marko"',
        "send_btn": "Pošalji",
        "cmd_executed": "Komanda je izvršena.",
        "cmd_playing": "Puštam: {track}",
        "cmd_busy": "Bot je zauzet u drugom kanalu.",
        "cmd_retry_in": " Pokušaj ponovo za ~{seconds}s.",

        # Error codes / messages
        "err_not_in_voice": "Nisi u glasovnom kanalu — uđi u VC pa pokušaj ponovo.",
        "err_no_dj_role": "Nemaš dozvolu (DJ rola je obavezna za ovu komandu).",
        "err_missing_permission": "Nemaš potrebne Discord permisije za ovu radnju.",
        "err_target_not_in_voice": "Korisnik nije u glasovnom kanalu.",
        "err_ambiguous_user": "Pronađeno je više korisnika sa tim imenom — preciziraj.",
        "err_hierarchy_error": "Nemaš veću ulogu od ciljanog korisnika.",
        "err_empty_queue": "Red pesama je prazan.",
        "err_invalid_index": "Nevažeći broj pesme u redu.",
        "err_bot_busy": "Bot trenutno svira u drugom kanalu.",
        "err_unsupported_command": "Nepoznata ili nepodržana komanda.",
        "err_missing_query": "Nedostaje upit za komandu.",
        "err_rate_limited": "Previše komandi — sačekaj trenutak.",
        "err_too_fast": "Pričekaj par sekundi pre sledeće komande.",

        # Settings
        "settings_box_title": "Podešavanja",
        "mic_label": "Mikrofon",
        "mic_system_default": "Sistemski (podrazumevano)",
        "mic_refresh_tooltip": "Osveži listu mikrofona",
        "mic_scan_tooltip": "Skeniraj sve mikrofone i pokaži gde ima signala",
        "mic_test_btn": "Test mikrofona (4 s)",
        "mic_testing_btn": "Slušam… pričaj",
        "stt_mode_label": "STT režim",
        "model_size_label": "STT model size (lokalno)",
        "cloud_model_label": "Cloud model",
        "lang_label": "Jezik komandi i aplikacije",
        "lang_tooltip": "Jezik za prepoznavanje govora i interfejs aplikacije. Menja se odmah bez restarta.",
        "sens_label": "Osetljivost wake word-a",
        "sens_tooltip": "Osetljivost wake word-a: levo = strože (manje lažnih poziva), desno = osetljivije",
        "trigger_key_label": "Trigger taster (PTT)",
        "trigger_key_placeholder": "npr. K, F9 ili CTRL+K (prazno = isključeno)",
        "trigger_key_tooltip": "Globalni taster (radi i kad je aplikacija u pozadini).\nPush-to-talk: drži taster da bi snimala, pusti da stane.\nToggle: jedan pritisak uključi, drugi isključi.",
        "trigger_mode_ptt": "Push-to-talk (drži)",
        "trigger_mode_toggle": "Toggle (uključi/isključi)",
        "sound_effects_label": "Zvučni efekti (wake + komanda)",
        "listen_only_vc_label": "Slušaj samo dok sam u voice kanalu",
        "autostart_label": "Pokreni sa Windows-om",
        "save_settings_btn": "Sačuvaj podešavanja",
        "settings_saved_msg": "Podešavanja su sačuvana.",

        # Updates
        "checking_updates": "Provera ažuriranja…",
        "app_up_to_date": "Aplikacija je ažurna.",
        "update_available": "Verzija {version} je dostupna — preuzimam…",
        "update_ready": "Verzija {version} je spremna za instalaciju.",
        "update_install_prompt": "Verzija {version} je preuzeta i verifikovana.\n\nInstalirati sada? Aplikacija će se zatvoriti.",
    },
    "en": {
        # App
        "app_title": "Kortik Listener",
        "logged_in": "Logged In",
        "not_logged_in": "Not Logged In",
        "discord_user": "Discord ID: {user_id}",
        "device_info": "Discord ID: {user_id} · Device {device_id}",

        # Pairing
        "pairing_box_title": "Confirm code on dashboard",
        "pair_device_btn": "Pair Device",
        "device_name_label": "Device Name (as seen on dashboard)",
        "device_name_placeholder": "e.g. My PC / Work Laptop",
        "pairing_start": "Starting pairing…",
        "pairing_waiting": "Waiting for dashboard approval… (code valid for 10 min)",
        "pairing_hint": "Click 'Pair Device' to generate a pairing code.",
        "pairing_success": "Device successfully paired.",
        "pairing_failed": "Pairing failed: {error}",
        "open_dashboard_btn": "Open Dashboard",
        "unlink_device_btn": "Unlink Device",
        "unlink_confirm_title": "Unlink Device",
        "unlink_confirm_msg": "Are you sure you want to unlink this device from your Discord account?",
        "unlinked_msg": "Device unlinked.",

        # Status
        "status_box_title": "Status",
        "bot_online": "Bot: Online",
        "bot_offline": "Bot: Offline",
        "vc_in": "VC: {channel}  (Server {guild})",
        "vc_not_in": "VC: Not in a voice channel",
        "busy_free": "Status: Bot is idle",
        "busy_other_vc": "Status: Bot is playing in another channel",
        "plugin_active": "Plugin: Enabled",
        "plugin_disabled": "Plugin: Disabled on server",
        "plugin_unknown": "Plugin: Unknown",
        "listening_active": "🎙️ Listening — waiting for 'Hey Jarvis'",
        "listening_stopped": "⏸️ Listening stopped",
        "listening_not_in_vc": "⏸️ Listening stopped · not in voice channel",
        "listening_ptt_active": "🎙️ PTT: Recording… release key to send",
        "listening_ptt_off": "⏸️ PTT: Recording cancelled",
        "heard_wake": "👂 Heard '{keyword}' — speak command…",
        "wake_only": "👂 Wake word detected — awaiting command.",

        # Listening controls
        "listen_wake_checkbox": "Listen for wake word 'Hey Jarvis'",
        "listen_btn_start": "Start Listening",
        "listen_btn_stop": "Stop Listening",
        "listen_mic_level_tooltip": "Microphone level while listening",

        # Test command
        "test_cmd_box": "Test Command",
        "test_cmd_placeholder": 'e.g. "play bohemian rhapsody", "skip", "jump 2" or "mute John"',
        "send_btn": "Send",
        "cmd_executed": "Command executed.",
        "cmd_playing": "Playing: {track}",
        "cmd_busy": "Bot is busy playing in another channel.",
        "cmd_retry_in": " Try again in ~{seconds}s.",

        # Error codes / messages
        "err_not_in_voice": "You are not in a voice channel — join a VC and try again.",
        "err_no_dj_role": "Permission denied (DJ role is required for this command).",
        "err_missing_permission": "You lack the required Discord permissions for this action.",
        "err_target_not_in_voice": "Target user is not in a voice channel.",
        "err_ambiguous_user": "Multiple users found matching that name — please specify.",
        "err_hierarchy_error": "Cannot target user with higher or equal role hierarchy.",
        "err_empty_queue": "The music queue is currently empty.",
        "err_invalid_index": "Invalid track number in queue.",
        "err_bot_busy": "Bot is currently playing in another voice channel.",
        "err_unsupported_command": "Unknown or unsupported command.",
        "err_missing_query": "Missing query for command.",
        "err_rate_limited": "Too many commands — please wait a moment.",
        "err_too_fast": "Please wait a few seconds before sending another command.",

        # Settings
        "settings_box_title": "Settings",
        "mic_label": "Microphone",
        "mic_system_default": "System Default",
        "mic_refresh_tooltip": "Refresh microphone list",
        "mic_scan_tooltip": "Scan all microphones for signal",
        "mic_test_btn": "Test Microphone (4s)",
        "mic_testing_btn": "Listening… speak now",
        "stt_mode_label": "STT Mode",
        "model_size_label": "Local STT Model Size",
        "cloud_model_label": "Cloud Model",
        "lang_label": "Command & UI Language",
        "lang_tooltip": "Speech recognition and app interface language. Applies immediately without restart.",
        "sens_label": "Wake Word Sensitivity",
        "sens_tooltip": "Wake word sensitivity: left = stricter (fewer false wakes), right = more sensitive",
        "trigger_key_label": "Trigger Hotkey (PTT)",
        "trigger_key_placeholder": "e.g. K, F9 or CTRL+K (empty = disabled)",
        "trigger_key_tooltip": "Global hotkey (works when app is in background).\nPush-to-talk: hold key while speaking, release to stop.\nToggle: one press starts recording, next cancels.",
        "trigger_mode_ptt": "Push-to-talk (hold)",
        "trigger_mode_toggle": "Toggle (on/off)",
        "sound_effects_label": "Sound Effects (wake + command)",
        "listen_only_vc_label": "Listen only while in voice channel",
        "autostart_label": "Launch on Windows startup",
        "save_settings_btn": "Save Settings",
        "settings_saved_msg": "Settings saved successfully.",

        # Updates
        "checking_updates": "Checking for updates…",
        "app_up_to_date": "App is up to date.",
        "update_available": "Version {version} is available — downloading…",
        "update_ready": "Version {version} is ready to install.",
        "update_install_prompt": "Version {version} downloaded and verified.\n\nInstall now? The app will close.",
    },
}


class I18nManager(QObject):
    language_changed = Signal(str)

    def __init__(self, default_lang: str = "sr"):
        super().__init__()
        self._current_lang = default_lang if default_lang in TRANSLATIONS else "en"

    @property
    def current_language(self) -> str:
        return self._current_lang

    def set_language(self, lang: str) -> None:
        clean = (lang or "sr").strip().lower()
        if clean not in SUPPORTED_LANGUAGES and clean != "auto":
            clean = "en"
        if self._current_lang != clean:
            self._current_lang = clean
            self.language_changed.emit(clean)

    def tr(self, key: str, default: Optional[str] = None, **kwargs: Any) -> str:
        lang_catalog = TRANSLATIONS.get(self._current_lang) or TRANSLATIONS.get("en", {})
        text = lang_catalog.get(key)
        if text is None:
            # Fallback to English, then Serbian
            text = TRANSLATIONS.get("en", {}).get(key, TRANSLATIONS.get("sr", {}).get(key, default or key))
        if kwargs and text:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text or default or key


# Global singleton instance
i18n = I18nManager()


def tr(key: str, default: Optional[str] = None, **kwargs: Any) -> str:
    """Convenience helper to translate a key using the global i18n instance."""
    return i18n.tr(key, default, **kwargs)


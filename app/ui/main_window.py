# c:\Kortik\Kortik-Listener-App\app\ui\main_window.py
"""Glavni prozor Kortik Listener aplikacije (PySide6)."""
from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from PySide6.QtCore import QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.auth.device_flow import DeviceFlow
from app.config import AppPaths, Settings, save_settings
from app.core.parser import parse_command
from app.net.api import ApiError, ListenerApi
from app.security.storage import SecretStore
from app.ui.async_runner import AsyncRunner
from app.updater.manifest import needs_update, validate_manifest
from app.version import APP_NAME, APP_VERSION, UPDATE_CHANNEL, UPDATE_PUBLIC_KEY_HEX

STYLE = """
QMainWindow, QWidget { background: #0f1117; color: #e8eaf0; font-size: 13px; }
QLabel#title { font-size: 22px; font-weight: 700; color: #ffffff; }
QLabel#subtitle { color: #9aa3b2; }
QLabel#code { font-size: 34px; font-weight: 800; letter-spacing: 8px; color: #8b5cf6; }
QLabel#pill { background: #1b1f2a; border: 1px solid #2a3040; border-radius: 10px; padding: 6px 12px; }
QLabel#ok { color: #34d399; }
QLabel#warn { color: #fbbf24; }
QLabel#err { color: #f87171; }
QPushButton { background: #6d28d9; border: none; border-radius: 8px; padding: 9px 16px; font-weight: 600; }
QPushButton:hover { background: #7c3aed; }
QPushButton:disabled { background: #2a3040; color: #6b7280; }
QPushButton#ghost { background: #1b1f2a; border: 1px solid #2a3040; }
QLineEdit, QComboBox { background: #151922; border: 1px solid #2a3040; border-radius: 8px; padding: 7px; }
QGroupBox { border: 1px solid #2a3040; border-radius: 10px; margin-top: 12px; padding: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; color: #9aa3b2; }
"""

_LANGUAGE_CHOICES = [
    "auto", "sr", "en", "hr", "bs", "mk", "sl",
    "de", "fr", "es", "it", "pt", "nl", "ru", "tr", "uk", "pl",
    "cs", "sk", "bg", "hu", "ro", "sv", "da", "no", "fi", "el",
    "ar", "hi", "zh", "ja", "ko",
]


class UiSignals(QObject):
    pairing_code = Signal(dict)
    pairing_error = Signal(str)
    pairing_done = Signal(dict)
    auth_ready = Signal(dict)
    session_error = Signal(str)
    heartbeat = Signal(dict)
    command_result = Signal(dict)
    update_info = Signal(object)
    update_ready = Signal(object)
    listener_event = Signal(object)
    listen_level = Signal(int)
    hotkey_pressed = Signal()
    hotkey_released = Signal()


class MainWindow(QMainWindow):
    HEARTBEAT_INTERVAL_MS = 15000

    def __init__(
        self,
        paths: AppPaths,
        settings: Settings,
        api: ListenerApi,
        store: SecretStore,
        flow: DeviceFlow,
        runner: AsyncRunner,
        logger: Any,
    ):
        super().__init__()
        self.paths = paths
        self.settings = settings
        self.api = api
        self.store = store
        self.flow = flow
        self.runner = runner
        self.logger = logger

        self.access_token: Optional[str] = None
        self.token_expires_at: float = 0.0
        self.last_heartbeat: Dict[str, Any] = {}
        self.pending_update: Optional[Dict[str, Any]] = None
        self.listener_service: Any = None
        self._hotkey: Any = None

        self.signals = UiSignals()
        self._wire_signals()

        self.setWindowTitle(f"{APP_NAME} {APP_VERSION}")
        self.resize(940, 660)
        self.setStyleSheet(STYLE)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_connect_page())
        self.stack.addWidget(self._build_dashboard_page())
        self.setCentralWidget(self.stack)

        self.heartbeat_timer = QTimer(self)
        self.heartbeat_timer.setInterval(self.HEARTBEAT_INTERVAL_MS)
        self.heartbeat_timer.timeout.connect(self._heartbeat_tick)

        self._restore_session()
        self._check_updates()

    def _wire_signals(self) -> None:
        self.signals.pairing_code.connect(self._on_pairing_code)
        self.signals.pairing_error.connect(self._on_pairing_error)
        self.signals.pairing_done.connect(self._on_pairing_done)
        self.signals.auth_ready.connect(self._on_auth_ready)
        self.signals.session_error.connect(self._on_session_error)
        self.signals.heartbeat.connect(self._on_heartbeat)
        self.signals.command_result.connect(self._on_command_result)
        self.signals.update_info.connect(self._on_update_info)
        self.signals.update_ready.connect(self._on_update_ready)
        self.signals.listener_event.connect(self._on_listener_event)
        self.signals.listen_level.connect(self._on_listen_level)
        self.signals.hotkey_pressed.connect(self._on_hotkey_pressed)
        self.signals.hotkey_released.connect(self._on_hotkey_released)

    @staticmethod
    def _set_status(label: QLabel, text: str, kind: str = "") -> None:
        label.setText(text)
        label.setObjectName(kind)
        label.style().unpolish(label)
        label.style().polish(label)

    # ── Sesija ──────────────────────────────────────────────────────────────
    def _restore_session(self) -> None:
        creds = self.store.load() or {}
        if creds.get("device_secret") and creds.get("refresh_token"):
            self.stack.setCurrentWidget(self.dashboard_page)
            self._set_status(self.conn_status, "Obnavljam sesiju…", "warn")
            self.runner.submit(self._task_refresh_session())
        else:
            self.stack.setCurrentWidget(self.connect_page)
            default_name = self.settings.device_name or os.environ.get("COMPUTERNAME", "Windows PC")
            self.device_name_edit.setText(default_name)

    async def _task_refresh_session(self) -> None:
        try:
            await self._ensure_token(force=True)
            self.signals.auth_ready.emit(self.store.load() or {})
            await self._heartbeat_once()
        except ApiError as e:
            if e.status in (401, 403):
                self.signals.session_error.emit("Sesija je istekla — upari uređaj ponovo.")
            else:
                self.signals.session_error.emit(e.message)
        except Exception as e:
            self.signals.session_error.emit(f"Neočekivana greška: {e}")

    async def _ensure_token(self, force: bool = False) -> str:
        if not force and self.access_token and time.time() < self.token_expires_at - 30:
            return self.access_token

        creds = self.store.load() or {}
        if not creds.get("refresh_token") or not creds.get("device_id"):
            raise ApiError(401, "no_session", "Nema sačuvane sesije.")

        data = await self.flow.refresh(creds["device_id"], creds["refresh_token"])
        self.access_token = str(data.get("access_token") or "")
        self.token_expires_at = time.time() + int(data.get("expires_in") or 900)
        if not self.access_token:
            raise ApiError(500, "no_token", "Server nije vratio pristupni token.")
        return self.access_token

    # ── Heartbeat ───────────────────────────────────────────────────────────
    def _heartbeat_tick(self) -> None:
        if self.stack.currentWidget() is not self.dashboard_page:
            return
        self.runner.submit(self._heartbeat_once())

    async def _heartbeat_once(self) -> None:
        try:
            token = await self._ensure_token()
            data = await self.api.heartbeat(
                token,
                app_version=APP_VERSION,
                listening=bool(getattr(self, "listen_check", None) and self.listen_check.isChecked()),
                device_name=self.settings.device_name,
            )
            self.last_heartbeat = data
            self.signals.heartbeat.emit(data)
        except ApiError as e:
            if e.status == 401:
                try:
                    token = await self._ensure_token(force=True)
                    data = await self.api.heartbeat(token, app_version=APP_VERSION)
                    self.signals.heartbeat.emit(data)
                    return
                except Exception:
                    pass
            self.signals.session_error.emit(e.message)
        except Exception as e:
            self.signals.session_error.emit(f"Heartbeat greška: {e}")

    # ── Komande ─────────────────────────────────────────────────────────────
    def _send_command(self) -> None:
        text = self.command_edit.text().strip()
        if not text:
            return
        parsed = parse_command(text)
        if parsed is None:
            command, query = "play", text
        else:
            command, query = parsed
        self.command_edit.clear()
        self._set_status(self.command_status, f"Šaljem: {command} {query}".strip(), "warn")
        self.runner.submit(self._task_command(command, query))

    async def _task_command(self, command: str, query: str) -> None:
        try:
            token = await self._ensure_token()
            secret = (self.store.load() or {}).get("device_secret") or ""
            result = await self.api.send_command(token, secret, command, query)
            self.signals.command_result.emit(result)
        except ApiError as e:
            self.signals.command_result.emit(
                {"status": e.code, "message": e.message, "http_status": e.status}
            )
        except Exception as e:
            self.signals.command_result.emit({"status": "error", "message": str(e), "http_status": 0})

    # ── Update ──────────────────────────────────────────────────────────────
    def _check_updates(self) -> None:
        self.runner.submit(self._task_check_updates())

    async def _task_check_updates(self) -> None:
        try:
            manifest = await self.api.check_update(UPDATE_CHANNEL)
        except Exception:
            return
        if manifest:
            self.signals.update_info.emit(manifest)

    # ── Connect page ────────────────────────────────────────────────────────
    def _build_connect_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(40, 34, 40, 34)
        layout.setSpacing(12)

        title = QLabel(APP_NAME)
        title.setObjectName("title")
        subtitle = QLabel(
            "Upari ovaj računar sa svojim Discord nalogom. Wake word i prepoznavanje "
            "komandi rade lokalno — audio ne napušta tvoj PC."
        )
        subtitle.setWordWrap(True)
        subtitle.setObjectName("subtitle")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        form = QFormLayout()
        self.device_name_edit = QLineEdit()
        self.device_name_edit.setPlaceholderText("npr. Ivanov PC")
        form.addRow("Ime uređaja", self.device_name_edit)
        layout.addLayout(form)

        self.pair_btn = QPushButton("Upari uređaj")
        self.pair_btn.clicked.connect(self._start_pairing)
        layout.addWidget(self.pair_btn)

        box = QGroupBox("Potvrdi kod na dashboardu")
        box_layout = QVBoxLayout(box)
        self.code_label = QLabel("——————")
        self.code_label.setObjectName("code")
        self.code_label.setAlignment(Qt.AlignCenter)
        box_layout.addWidget(self.code_label)
        self.code_hint = QLabel("Klikni „Upari uređaj“ da dobiješ kod.")
        self.code_hint.setObjectName("subtitle")
        self.code_hint.setWordWrap(True)
        box_layout.addWidget(self.code_hint)
        self.open_dash_btn = QPushButton("Otvori dashboard")
        self.open_dash_btn.setObjectName("ghost")
        self.open_dash_btn.setEnabled(False)
        self.open_dash_btn.clicked.connect(self._open_verification_uri)
        box_layout.addWidget(self.open_dash_btn)
        layout.addWidget(box)

        self.conn_status = QLabel("")
        self.conn_status.setWordWrap(True)
        layout.addWidget(self.conn_status)
        layout.addStretch(1)

        self._verification_uri = ""
        self.connect_page = page
        return page

    # ── Pairing ─────────────────────────────────────────────────────────────
    def _start_pairing(self) -> None:
        name = self.device_name_edit.text().strip() or os.environ.get("COMPUTERNAME", "Windows PC")
        self.settings.device_name = name
        save_settings(self.paths, self.settings)
        self.pair_btn.setEnabled(False)
        self._set_status(self.conn_status, "Započinjem uparivanje…", "warn")
        self.runner.submit(self._task_pair(name))

    async def _task_pair(self, name: str) -> None:
        try:
            session = await self.flow.start(name, APP_VERSION)
            self.signals.pairing_code.emit(
                {
                    "user_code": session.user_code,
                    "verification_uri": session.verification_uri,
                    "expires_in": session.expires_in,
                }
            )
            data = await self.flow.wait_for_token()
            self.signals.pairing_done.emit(data)
        except ApiError as e:
            self.signals.pairing_error.emit(e.message)
        except Exception as e:
            self.signals.pairing_error.emit(f"Uparivanje nije uspelo: {e}")

    def _on_pairing_code(self, data: dict) -> None:
        self.code_label.setText(" ".join(str(data.get("user_code") or "")))
        self._verification_uri = str(data.get("verification_uri") or "")
        self.open_dash_btn.setEnabled(bool(self._verification_uri))
        self._set_status(
            self.conn_status,
            "Čekam potvrdu na dashboardu… (kod važi 10 minuta)",
            "warn",
        )

    def _open_verification_uri(self) -> None:
        if self._verification_uri:
            QDesktopServices.openUrl(QUrl(self._verification_uri))

    def _on_pairing_done(self, data: dict) -> None:
        self.pair_btn.setEnabled(True)
        self.code_label.setText("✅")
        self._set_status(self.conn_status, "Uređaj je uspešno uparen.", "ok")
        self.signals.auth_ready.emit(data)

    def _on_pairing_error(self, message: str) -> None:
        self.pair_btn.setEnabled(True)
        self._set_status(self.conn_status, message, "err")

    def _on_auth_ready(self, data: dict) -> None:
        self.stack.setCurrentWidget(self.dashboard_page)
        self.heartbeat_timer.start()
        user_id = (data or {}).get("user_id")
        self.user_label.setText(f"Discord ID: {user_id}" if user_id else "Ulogovan")
        self.runner.submit(self._heartbeat_once())

        # Vrati prethodno stanje slusanja (bez modalnih dijaloga — ne blokira start).
        if getattr(self.settings, "listening", False):
            self._start_listening()

    def _on_session_error(self, message: str) -> None:
        if self.stack.currentWidget() is self.dashboard_page:
            self.heartbeat_timer.stop()
        self.pair_btn.setEnabled(True)
        self._set_status(self.conn_status, message, "err")

    # ── Dashboard ───────────────────────────────────────────────────────────
    def _build_dashboard_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel(APP_NAME)
        title.setObjectName("title")
        version = QLabel(f"v{APP_VERSION} · {UPDATE_CHANNEL}")
        version.setObjectName("pill")
        header.addWidget(title)
        header.addStretch(1)
        header.addWidget(version)
        layout.addLayout(header)

        self.user_label = QLabel("Ulogovan")
        self.user_label.setObjectName("subtitle")
        layout.addWidget(self.user_label)

        status_box = QGroupBox("Status")
        status_layout = QVBoxLayout(status_box)
        self.bot_label = QLabel("Bot: —")
        self.vc_label = QLabel("VC: —")
        self.busy_label = QLabel("Zauzetost: —")
        self.plugin_label = QLabel("Plugin: —")
        self.voice_label = QLabel("Slušanje: isključeno")
        for widget in (self.bot_label, self.vc_label, self.busy_label, self.plugin_label, self.voice_label):
            status_layout.addWidget(widget)
        layout.addWidget(status_box)

        listen_row = QHBoxLayout()
        self.listen_check = QCheckBox("Slušam wake word „Hey Jarvis“")
        self.listen_check.setChecked(False)
        self.listen_check.stateChanged.connect(self._on_listen_toggle)
        self.listen_btn = QPushButton("Uključi slušanje")
        self.listen_btn.setObjectName("ghost")
        self.listen_btn.clicked.connect(self._toggle_listen_button)
        listen_row.addWidget(self.listen_check)
        listen_row.addWidget(self.listen_btn)
        self.listen_level = QProgressBar()
        self.listen_level.setRange(0, 100)
        self.listen_level.setValue(0)
        self.listen_level.setTextVisible(False)
        self.listen_level.setFixedHeight(8)
        self.listen_level.setFixedWidth(120)
        self.listen_level.setToolTip("Nivo mikrofona dok slušam")
        listen_row.addWidget(self.listen_level)
        listen_row.addStretch(1)
        layout.addLayout(listen_row)

        cmd_box = QGroupBox("Test komanda")
        cmd_layout = QVBoxLayout(cmd_box)
        cmd_row = QHBoxLayout()
        self.command_edit = QLineEdit()
        self.command_edit.setPlaceholderText('npr. "pusti senidah bez tebe" ili "skip"')
        self.command_edit.returnPressed.connect(self._send_command)
        self.send_btn = QPushButton("Pošalji")
        self.send_btn.clicked.connect(self._send_command)
        cmd_row.addWidget(self.command_edit, 1)
        cmd_row.addWidget(self.send_btn)
        cmd_layout.addLayout(cmd_row)
        self.command_status = QLabel("")
        self.command_status.setWordWrap(True)
        cmd_layout.addWidget(self.command_status)
        layout.addWidget(cmd_box)

        settings_box = QGroupBox("Podešavanja")
        form = QFormLayout(settings_box)
        mic_row = QHBoxLayout()
        self.mic_combo = QComboBox()
        mic_row.addWidget(self.mic_combo, 1)
        mic_refresh = QPushButton("↻")
        mic_refresh.setObjectName("ghost")
        mic_refresh.setFixedWidth(38)
        mic_refresh.setToolTip("Osveži listu mikrofona")
        mic_refresh.clicked.connect(self._reload_mics)
        mic_row.addWidget(mic_refresh)
        mic_scan = QPushButton("🔍")
        mic_scan.setObjectName("ghost")
        mic_scan.setFixedWidth(38)
        mic_scan.setToolTip("Skeniraj sve mikrofone i pokaži gde ima signala")
        mic_scan.clicked.connect(self._scan_mics)
        mic_row.addWidget(mic_scan)
        form.addRow("Mikrofon", mic_row)

        self.mic_test_btn = QPushButton("Test mikrofona (4 s)")
        self.mic_test_btn.setObjectName("ghost")
        self.mic_test_btn.clicked.connect(self._test_mic)
        self.mic_level = QProgressBar()
        self.mic_level.setRange(0, 100)
        self.mic_level.setValue(0)
        self.mic_level.setTextVisible(False)
        self.mic_level.setFixedHeight(8)
        mic_test_row = QHBoxLayout()
        mic_test_row.addWidget(self.mic_test_btn)
        mic_test_row.addWidget(self.mic_level, 1)
        form.addRow("", mic_test_row)
        self.stt_combo = QComboBox()
        self.stt_combo.addItems(["local", "cloud"])
        self.stt_combo.setCurrentText(self.settings.stt_mode)
        self.stt_combo.currentTextChanged.connect(self._on_stt_mode_changed)
        form.addRow("STT režim", self.stt_combo)
        self.model_size_combo = QComboBox()
        self.model_size_combo.addItems(["small", "base", "tiny"])
        self.model_size_combo.setCurrentText(getattr(self.settings, "stt_model_size", "small"))
        self.model_size_combo.setToolTip(
            "small = najbolje za srpski (~244 MB RAM)\n"
            "base = kompromis (~74 MB)\n"
            "tiny = najmanje RAM-a (~39 MB), slabija tačnost"
        )
        self.model_size_label = QLabel("STT model size (lokalno)")
        form.addRow(self.model_size_label, self.model_size_combo)
        self.cloud_model_combo = QComboBox()
        self.cloud_model_combo.addItem("Large Turbo (brži)", "whisper-large-v3-turbo")
        self.cloud_model_combo.addItem("Large (najtačniji)", "whisper-large-v3")
        current_cloud = getattr(self.settings, "stt_cloud_model", "whisper-large-v3-turbo")
        cloud_idx = self.cloud_model_combo.findData(current_cloud)
        if cloud_idx >= 0:
            self.cloud_model_combo.setCurrentIndex(cloud_idx)
        self.cloud_model_combo.setToolTip(
            "Groq Whisper model za cloud STT (mnogo tačniji od lokalnog).\n"
            "Large Turbo = brži, skoro isto tačan.\n"
            "Large = najtačniji, malo sporiji."
        )
        self.cloud_model_label = QLabel("Cloud model")
        form.addRow(self.cloud_model_label, self.cloud_model_combo)
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(_LANGUAGE_CHOICES)
        lang_index = self.lang_combo.findText(self.settings.language)
        if lang_index >= 0:
            self.lang_combo.setCurrentIndex(lang_index)
        else:
            self.lang_combo.addItem(self.settings.language)
            self.lang_combo.setCurrentIndex(self.lang_combo.count() - 1)
        self.lang_combo.setToolTip(
            "Jezik u kom pričaš komande (auto = sam prepozna). "
            "Za srpski ostavi 'sr' — tako Whisper najbolje prepoznaje."
        )
        form.addRow("Jezik komandi", self.lang_combo)
        self.sens_slider = QSlider(Qt.Horizontal)
        self.sens_slider.setRange(0, 100)
        self.sens_slider.setValue(int(round(self.settings.sensitivity * 100)))
        self.sens_slider.setToolTip(
            "Osetljivost wake word-a: levo = strože (manje lažnih poziva), desno = osetljivije"
        )
        form.addRow("Osetljivost wake word-a", self.sens_slider)
        self.trigger_key_edit = QLineEdit()
        self.trigger_key_edit.setText(getattr(self.settings, "trigger_key", "") or "")
        self.trigger_key_edit.setPlaceholderText('npr. K, F9 ili CTRL+K (prazno = isključeno)')
        self.trigger_key_edit.setToolTip(
            "Globalni taster (radi i kad je aplikacija u pozadini).\n"
            "Push-to-talk: drži taster da bi snimala, pusti da stane.\n"
            "Toggle: jedan pritisak uključi, drugi isključi."
        )
        self.trigger_mode_combo = QComboBox()
        self.trigger_mode_combo.addItem("Push-to-talk (drži)", "push_to_talk")
        self.trigger_mode_combo.addItem("Toggle (uključi/isključi)", "toggle")
        mode_idx = self.trigger_mode_combo.findData(
            getattr(self.settings, "trigger_mode", "push_to_talk") or "push_to_talk"
        )
        if mode_idx >= 0:
            self.trigger_mode_combo.setCurrentIndex(mode_idx)
        trigger_row = QHBoxLayout()
        trigger_row.addWidget(self.trigger_key_edit, 1)
        trigger_row.addWidget(self.trigger_mode_combo)
        form.addRow("Trigger taster (PTT)", trigger_row)
        self.sound_check = QCheckBox("Zvučni efekti (wake + komanda)")
        self.sound_check.setChecked(getattr(self.settings, "sound_effects", True))
        form.addRow("", self.sound_check)
        self.only_vc_check = QCheckBox("Slušaj samo dok sam u voice kanalu")
        self.only_vc_check.setChecked(self.settings.listen_only_in_voice)
        form.addRow("", self.only_vc_check)
        self.autostart_check = QCheckBox("Pokreni sa Windows-om")
        self.autostart_check.setChecked(self.settings.autostart)
        form.addRow("", self.autostart_check)
        save_btn = QPushButton("Sačuvaj podešavanja")
        save_btn.setObjectName("ghost")
        save_btn.clicked.connect(self._save_settings_ui)
        form.addRow("", save_btn)
        layout.addWidget(settings_box)

        self.update_label = QLabel("Provera ažuriranja…")
        self.update_label.setWordWrap(True)
        layout.addWidget(self.update_label)

        footer = QHBoxLayout()
        dash_btn = QPushButton("Otvori dashboard")
        dash_btn.setObjectName("ghost")
        dash_btn.clicked.connect(self._open_dashboard)
        unlink_btn = QPushButton("Odjavi uređaj")
        unlink_btn.setObjectName("ghost")
        unlink_btn.clicked.connect(self._unlink_device)
        footer.addWidget(dash_btn)
        footer.addStretch(1)
        footer.addWidget(unlink_btn)
        layout.addLayout(footer)

        self.dashboard_page = page
        self._on_stt_mode_changed(self.stt_combo.currentText())
        self._reload_mics()
        return page

    def _on_stt_mode_changed(self, mode: str) -> None:
        """Prikazi odgovarajuci dropdown (local -> model size, cloud -> Groq model)."""
        cloud = (mode or "").strip().lower() == "cloud"
        for widget in (getattr(self, "model_size_combo", None), getattr(self, "model_size_label", None)):
            if widget is not None:
                widget.setVisible(not cloud)
        for widget in (getattr(self, "cloud_model_combo", None), getattr(self, "cloud_model_label", None)):
            if widget is not None:
                widget.setVisible(cloud)

    # ── Slots ───────────────────────────────────────────────────────────────
    def _on_heartbeat(self, data: dict) -> None:
        bot_online = data.get("bot_online")
        self._set_status(
            self.bot_label,
            "Bot: online" if bot_online else "Bot: offline",
            "ok" if bot_online else "err",
        )

        in_voice = bool(data.get("in_voice"))
        if in_voice:
            channel = data.get("channel_name") or data.get("channel_id")
            guild = data.get("guild_id")
            self._set_status(self.vc_label, f"VC: {channel}  (server {guild})", "ok")
        else:
            self._set_status(self.vc_label, "VC: nisi u glasovnom kanalu", "warn")

        busy = data.get("busy")
        self._set_status(
            self.busy_label,
            "Zauzetost: bot svira u drugom kanalu" if busy else "Zauzetost: bot je slobodan",
            "warn" if busy else "ok",
        )

        plugin = data.get("plugin_enabled")
        if plugin is None:
            self._set_status(self.plugin_label, "Plugin: nepoznato", "warn")
        else:
            self._set_status(
                self.plugin_label,
                "Plugin: uključen" if plugin else "Plugin: isključen na serveru",
                "ok" if plugin else "warn",
            )

        # Ne diramo korisnikovu odluku — samo prikazujemo stanje i razlog
        if self.listener_service is not None:
            self._set_status(self.voice_label, "🎙️ Slušam — čekam „Hey Jarvis“", "ok")
            self.listen_btn.setText("Zaustavi slušanje")
        elif self.settings.listen_only_in_voice and not in_voice:
            self._set_status(self.voice_label, "⏸️ Slušanje isključeno · nisi u voice kanalu", "warn")
            self.listen_btn.setText("Uključi slušanje")
        else:
            self._set_status(self.voice_label, "⏸️ Slušanje je isključeno", "warn")
            self.listen_btn.setText("Uključi slušanje")

        user_id = data.get("user_id")
        if user_id:
            self.user_label.setText(f"Discord ID: {user_id} · uređaj {data.get('device_id', '')}")

    def _on_command_result(self, data: dict) -> None:
        status = str(data.get("status") or "error")
        message = str(data.get("message") or "")

        if status == "success":
            track = data.get("track")
            text = message or (f"Puštam: {track}" if track else "Komanda je izvršena.")
            self._set_status(self.command_status, f"✅ {text}", "ok")
        elif status == "busy":
            retry = data.get("retry_after")
            self._set_status(
                self.command_status,
                "🎧 " + (message or "Bot je zauzet u drugom kanalu.")
                + (f" Pokušaj ponovo za ~{retry}s." if retry else ""),
                "warn",
            )
        elif status in ("not_in_voice", "missing_query", "unsupported_command", "too_fast", "rate_limited", "disabled"):
            self._set_status(self.command_status, "⚠️ " + (message or status), "warn")
        else:
            self._set_status(self.command_status, "❌ " + (message or status), "err")

    def _on_update_info(self, manifest: dict) -> None:
        if not isinstance(manifest, dict):
            return
        if not needs_update(manifest, APP_VERSION):
            self._set_status(self.update_label, "Aplikacija je ažurna.", "ok")
            return

        ok, reason = validate_manifest(manifest, APP_VERSION, UPDATE_PUBLIC_KEY_HEX)
        if ok:
            self.pending_update = manifest
            self._set_status(
                self.update_label,
                f"Verzija {manifest.get('version')} je dostupna (potpis verifikovan) — preuzimam…",
                "warn",
            )
            self.runner.submit(self._task_prepare_update(manifest))
        else:
            self.pending_update = None
            self._set_status(
                self.update_label,
                f"Ažuriranje odbijeno ({reason}) — manifest nije verifikovan.",
                "warn",
            )

    async def _task_prepare_update(self, manifest: dict) -> None:
        from app.updater.installer import UpdateError, download_installer, verify_authenticode

        try:
            path = await download_installer(manifest, self.paths.updates)
        except UpdateError as e:
            self.signals.update_ready.emit({"error": str(e)})
            return
        except Exception as e:
            self.signals.update_ready.emit({"error": f"Neočekivana greška pri preuzimanju: {e}"})
            return

        signed, status = verify_authenticode(path)
        self.signals.update_ready.emit(
            {
                "manifest": manifest,
                "path": str(path),
                "signed": signed,
                "signature_status": status,
            }
        )

    def _on_update_ready(self, payload: dict) -> None:
        if not isinstance(payload, dict):
            return
        if payload.get("error"):
            self._set_status(self.update_label, f"Ažuriranje nije preuzeto: {payload['error']}", "err")
            return

        manifest = payload.get("manifest") or {}
        path = payload.get("path") or ""
        version = manifest.get("version")

        signed = bool(payload.get("signed"))
        if not signed:
            if getattr(self.settings, "require_authenticode", False):
                self._set_status(
                    self.update_label,
                    f"Verzija {version} nije Authenticode-potpisana "
                    f"({payload.get('signature_status')}) — blokirano podešavanjem.",
                    "err",
                )
                self.logger.error("Update odbijen: Authenticode status=%s", payload.get("signature_status"))
                return
            # Beta: manifest je vec Ed25519-verifikovan (sha256 unutra) -> dozvoljavamo
            self.logger.warning(
                "Update nije Authenticode-potpisan (%s); manifest je Ed25519-verifikovan -> nastavljam.",
                payload.get("signature_status"),
            )

        self._set_status(
            self.update_label,
            f"Verzija {version} je preuzeta i verifikovana — spremna za instalaciju.",
            "ok",
        )

        answer = QMessageBox.question(
            self,
            "Ažuriranje spremno",
            (
                f"Verzija {version} je preuzeta i verifikovana"
                f"{' (potpisana)' if signed else ' (Ed25519 manifest, bez Authenticode potpisa)'}.\n\n"
                "Instalirati sada? Aplikacija će se zatvoriti."
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return

        try:
            from app.updater.installer import launch_installer

            launch_installer(path)
        except Exception as e:
            QMessageBox.critical(self, "Greška", f"Installer nije pokrenut: {e}")
            return

        from PySide6.QtWidgets import QApplication

        QApplication.quit()

    def _toggle_listen_button(self) -> None:
        self.listen_check.setChecked(not self.listen_check.isChecked())

    def _on_listen_toggle(self, _state: int) -> None:
        if not self.listen_check.isChecked():
            self._stop_listening()
            return

        in_voice = bool((self.last_heartbeat or {}).get("in_voice"))

        # Ako mikrofon nije izabran — skeniraj i auto-izaberi onaj koji daje signal
        if not (self.mic_combo.currentData() or ""):
            if self._scan_mics(autoselect=True) < 50:
                QMessageBox.warning(
                    self,
                    "Mikrofon ne daje signal",
                    "Nijedan mikrofon nije dao signal tokom skeniranja.\n\n"
                    "1) Proveri Windows → Settings → Privacy → Microphone → "
                    "„Allow desktop apps“\n"
                    "2) Proveri da mikrofon nije mute u Windowsu\n"
                    "3) Ponovi skeniranje i pričaj tokom njega",
                )
                self.listen_check.blockSignals(True)
                self.listen_check.setChecked(False)
                self.listen_check.blockSignals(False)
                return

        if not in_voice and self.settings.listen_only_in_voice:
            answer = QMessageBox.question(
                self,
                "Nisi u voice kanalu",
                "Trenutno nisi u voice kanalu, a uključeno je „slušaj samo u VC“.\n\n"
                "Da slušam i van voice kanala?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                self.listen_check.blockSignals(True)
                self.listen_check.setChecked(False)
                self.listen_check.blockSignals(False)
                self._set_status(self.voice_label, "⏸️ Slušanje isključeno", "warn")
                return
            self.settings.listen_only_in_voice = False
            if hasattr(self, "only_vc_check"):
                self.only_vc_check.setChecked(False)
            save_settings(self.paths, self.settings)

        self._start_listening()

    # ── Mikrofon (izbor + test) ─────────────────────────────────────────────
    def _reload_mics(self) -> None:
        from app.audio.capture import list_input_devices

        current = self.settings.mic_device or ""
        self.mic_combo.blockSignals(True)
        self.mic_combo.clear()
        self.mic_combo.addItem("Sistemski (podrazumevano)", "")
        for device in list_input_devices():
            # cuvamo INDEKS (tacan uredjaj), a prikazujemo ime
            self.mic_combo.addItem(f"{device['index']} — {device['name']}", str(device["index"]))

        index = 0
        for i in range(self.mic_combo.count()):
            if self.mic_combo.itemData(i) == current:
                index = i
                break
        self.mic_combo.setCurrentIndex(index)
        self.mic_combo.blockSignals(False)

        if hasattr(self, "mic_test_btn"):
            self.mic_test_btn.setEnabled(self.mic_combo.count() > 1)

    def _scan_mics(self, autoselect: bool = False) -> int:
        """Testira svaki ulazni uredjaj ~1.2 s i pokaze peak RMS (dijagnostika)."""
        from PySide6.QtWidgets import QApplication

        from app.audio.capture import MicrophoneCapture, list_input_devices
        from app.audio.vad import rms as _rms

        devices = list_input_devices()
        if not devices:
            QMessageBox.warning(self, "Mikrofoni", "Nijedan ulazni uređaj nije pronađen.")
            return

        QApplication.setOverrideCursor(Qt.WaitCursor)
        rows = []
        try:
            for device in devices:
                capture = MicrophoneCapture(device=str(device["index"]))
                peak = 0
                try:
                    capture.start()
                    deadline = time.monotonic() + 1.2
                    while time.monotonic() < deadline:
                        chunk = capture.read(0.1)
                        if chunk:
                            peak = max(peak, int(_rms(chunk)))
                    rows.append((device["name"], peak, capture.device_label))
                except Exception as exc:
                    rows.append((device["name"], -1, f"greška: {exc}"))
                finally:
                    try:
                        capture.stop()
                    except Exception:
                        pass
        finally:
            QApplication.restoreOverrideCursor()

        rows.sort(key=lambda row: row[1], reverse=True)
        lines = []
        for name, peak, _label in rows:
            mark = "✔" if peak > 100 else ("~" if peak > 20 else "·")
            lines.append(f"{mark}  {peak:>5}  {name}")

        best_peak = rows[0][1] if rows else -1
        note = "Izaberi uređaj sa najvećim RMS-om (✔)."
        if autoselect and rows and best_peak >= 50:
            best_name = rows[0][0]
            for i in range(self.mic_combo.count()):
                if self.mic_combo.itemText(i).endswith(best_name):
                    self.mic_combo.setCurrentIndex(i)
                    self.settings.mic_device = self.mic_combo.currentData() or ""
                    save_settings(self.paths, self.settings)
                    note = f"Automatski izabran: {best_name} (RMS={best_peak})."
                    break

        QMessageBox.information(
            self,
            "Skeniranje mikrofona",
            "Peak RMS po uređaju (pričaj tokom skeniranja):\n\n"
            + "\n".join(lines)
            + f"\n\n{note}",
        )
        return best_peak

    def _detect_wake_word_in_pcm(self, pcm: bytes) -> str:
        """Provera wake word-a nad snimljenim audio baferom (uvek OpenWakeWord)."""
        if not pcm:
            return "nema audio podataka"

        try:
            from app.kws.openwakeword_kws import OpenWakeWordKws, threshold_from_sensitivity

            kws = OpenWakeWordKws(threshold=threshold_from_sensitivity(self.settings.sensitivity))
            if not OpenWakeWordKws.available(kws.model_dir):
                return f"model nije pronađen ({kws.model_dir})"
            kws.load()
            peak = kws.peak_score(pcm)
            verdict = "HEY JARVIS ✔" if peak >= kws.threshold else "nema fraze „Hey Jarvis“"
            return f"max skor {peak:.3f} (prag {kws.threshold}) → {verdict}"
        except Exception as exc:
            return f"greška: {exc}"

    def _test_mic(self) -> None:
        from PySide6.QtCore import QTimer

        from app.audio.capture import MicrophoneCapture
        from app.audio.vad import rms

        if getattr(self, "_mic_test_capture", None) is not None:
            return

        # Dok test radi, pauziraj live slušanje da isti uređaj ne otvorimo dva puta
        # (SteelSeries Sonar ume da vrati tišinu na drugom stream-u).
        self._resume_listening_after_test = self.listener_service is not None
        if self._resume_listening_after_test:
            self._stop_listening()

        if not (self.mic_combo.currentData() or ""):
            if self._scan_mics(autoselect=True) < 50:
                QMessageBox.warning(
                    self,
                    "Nema signala",
                    "Nijedan mikrofon nije dao signal. Proveri Windows privatnost "
                    "(Settings → Privacy → Microphone → Allow desktop apps) i da mikrofon nije mute.",
                )
                return

        capture = MicrophoneCapture(device=self.mic_combo.currentData() or None)
        try:
            capture.start()
        except Exception as exc:
            QMessageBox.warning(self, "Mikrofon", f"Ne mogu da otvorim mikrofon:\n{exc}")
            return

        self._mic_test_capture = capture
        self._mic_test_peak = 0
        self._mic_test_ticks = 0
        self._mic_test_pcm: list = []
        self.mic_test_btn.setEnabled(False)
        self.mic_test_btn.setText("Slušam… pričaj")

        def tick() -> None:
            # Ispraznimo SVE dostupne chunkove — ranije se čitao samo 1 po ticku
            # (100 ms), pa je test uzorkovao ~20% zvuka i „nekad čuo, nekad ne".
            try:
                while True:
                    chunk = capture.read(0.0)
                    if not chunk:
                        break
                    if self._mic_test_ticks < 3:  # grace: stream se stabilizuje (~300 ms)
                        continue
                    self._mic_test_pcm.append(chunk)
                    level = rms(chunk)
                    self._mic_test_peak = max(self._mic_test_peak, int(level))
                    self.mic_level.setValue(min(100, int(level / 60)))
            except Exception:
                pass
            self._mic_test_ticks += 1
            if self._mic_test_ticks < 40:  # ~4 s
                return

            self._mic_test_timer.stop()
            try:
                capture.stop()
            except Exception:
                pass
            self._mic_test_capture = None
            self.mic_test_btn.setEnabled(True)
            self.mic_test_btn.setText("Test mikrofona (4 s)")
            self.mic_level.setValue(0)

            peak = self._mic_test_peak
            if peak > 250:
                verdict = "Dobar signal ✔"
            elif peak > 60:
                verdict = "Tiho — pojačaj mikrofon ili priđi bliže."
            else:
                verdict = "Nema signala — verovatno pogrešan uređaj."

            wake = self._detect_wake_word_in_pcm(b"".join(self._mic_test_pcm))
            QMessageBox.information(
                self,
                "Test mikrofona",
                f"Peak RMS: {peak}\n{verdict}\n\nWake word: {wake}\n"
                "Savet: reci „Hey Jarvis“ blizu mikrofona; ako score/transkript ne raste, "
                "pojačaj mikrofon ili izaberi drugi uređaj (🔍).",
            )
            if self._resume_listening_after_test:
                self._start_listening()

        self._mic_test_timer = QTimer(self)
        self._mic_test_timer.timeout.connect(tick)
        self._mic_test_timer.start(100)

    def _start_listening(self) -> None:
        if self.listener_service is not None:
            return
        try:
            from app.audio.capture import MicrophoneCapture, available as mic_available
            from app.audio.vad import UtteranceRecorder, VadConfig
            from app.core.listener_core import ListenerCore
            from app.core.listener_service import ListenerService
            from app.kws.openwakeword_kws import OpenWakeWordKws, threshold_from_sensitivity
            from app.stt.base import create_stt

            if not mic_available():
                raise RuntimeError(
                    "Mikrofon nije dostupan (sounddevice / PortAudio nije instaliran)."
                )

            threshold = threshold_from_sensitivity(self.settings.sensitivity)

            # Wake word je UVEK akusticni OpenWakeWord model (nikad STT transkript).
            kws = OpenWakeWordKws(threshold=threshold)
            if not OpenWakeWordKws.available(kws.model_dir):
                raise RuntimeError(f"OpenWakeWord model nije dostupan ({kws.model_dir})")
            kws.load()

            async def _credentials():
                token = await self._ensure_token()
                secret = (self.store.load() or {}).get("device_secret") or ""
                return token, secret

            stt, note = create_stt(
                self.settings.stt_mode,
                self.settings.language,
                model_size=getattr(self.settings, "stt_model_size", "small"),
                cloud_model=getattr(self.settings, "stt_cloud_model", "whisper-large-v3-turbo"),
                api=self.api,
                credentials_provider=_credentials,
            )
            if note:
                if note in ("cloud", "local"):
                    self.logger.info("STT režim: %s", note)
                else:
                    self.logger.warning("STT: %s", note)
            if stt is None:
                raise RuntimeError(f"STT nije dostupan: {note}")

            recorder = UtteranceRecorder(VadConfig())
            core = ListenerCore(kws, recorder, stt)
            capture = MicrophoneCapture(device=self.mic_combo.currentData() or None)
            self.listener_service = ListenerService(
                core,
                capture,
                on_action=self._handle_listener_action,
                on_level=lambda level: self.signals.listen_level.emit(int(level)),
                on_error=lambda msg: self.signals.listener_event.emit({"kind": "error", "text": str(msg)}),
            )
            self.runner.submit(self.listener_service.start())
            self.listen_check.blockSignals(True)
            self.listen_check.setChecked(True)
            self.listen_check.blockSignals(False)
            self.listen_btn.setText("Zaustavi slušanje")
            self.settings.listening = True
            save_settings(self.paths, self.settings)
            self._apply_hotkey()
            self._set_status(
                self.voice_label,
                f"Slušanje: tražim „Hey Jarvis“ (STT={self.settings.stt_mode})",
                "ok",
            )
            self.logger.info(
                "Listening pokrenut (wake=oww, STT=%s, threshold=%.2f)",
                type(stt).__name__,
                threshold,
            )
            self.runner.submit(self._heartbeat_once())
        except Exception as e:
            self.logger.error("Ne mogu da uključim slušanje: %s", e)
            self.listener_service = None
            self.listen_check.blockSignals(True)
            self.listen_check.setChecked(False)
            self.listen_check.blockSignals(False)
            self._set_status(self.voice_label, f"Slušanje: neuspešno ({e})", "err")

    def _stop_listening(self) -> None:
        service, self.listener_service = self.listener_service, None
        if service is not None:
            try:
                self.runner.submit(service.stop())
            except Exception:
                pass
            self.logger.info("Listening zaustavljen.")
        self.listen_check.blockSignals(True)
        self.listen_check.setChecked(False)
        self.listen_check.blockSignals(False)
        if hasattr(self, "listen_btn"):
            self.listen_btn.setText("Uključi slušanje")
        self._remove_hotkey()
        self.settings.listening = False
        save_settings(self.paths, self.settings)
        self._set_status(self.voice_label, "⏸️ Slušanje je isključeno", "warn")
        self.runner.submit(self._heartbeat_once())

    async def _handle_listener_action(self, action: Any) -> None:
        kind = getattr(action, "kind", "")
        if kind == "wake":
            self.signals.listener_event.emit({"kind": "wake", "keyword": getattr(action, "keyword", "")})
        elif kind in ("wake_only", "text"):
            self.signals.listener_event.emit({"kind": kind, "text": getattr(action, "text", "")})
        elif kind == "command":
            self.signals.listener_event.emit(
                {
                    "kind": "command",
                    "command": getattr(action, "command", ""),
                    "query": getattr(action, "query", ""),
                }
            )
            await self._task_command(getattr(action, "command", ""), getattr(action, "query", ""))

    def _on_listen_level(self, level: int) -> None:
        if hasattr(self, "listen_level"):
            self.listen_level.setValue(max(0, min(100, int(level))))

    def _on_listener_event(self, payload: dict) -> None:
        kind = (payload or {}).get("kind")
        if getattr(self.settings, "sound_effects", True):
            try:
                from app.audio.sounds import play_command, play_wake

                if kind in ("wake", "ptt_active"):
                    play_wake()
                elif kind == "command":
                    play_command()
            except Exception:
                pass
        if kind == "wake":
            self._set_status(self.voice_label, f"👂 Čuo sam „{payload.get('keyword')}“ — govori…", "ok")
        elif kind == "ptt_active":
            self._set_status(self.voice_label, "🎙️ PTT: snimam… pusti taster", "ok")
        elif kind == "ptt_off":
            self._set_status(self.voice_label, "⏸️ PTT: snimanje isključeno", "warn")
        elif kind == "wake_only":
            self._set_status(self.voice_label, "👂 Samo wake word — čekam komandu.", "warn")
        elif kind == "text":
            self._set_status(
                self.voice_label,
                f"🤔 Prepoznato: „{payload.get('text')}“ (nije komanda)",
                "warn",
            )
        elif kind == "command":
            self._set_status(
                self.voice_label,
                f"🎙️ Komanda: {payload.get('command')} {payload.get('query')}".strip(),
                "ok",
            )
        elif kind == "error":
            # Petlja slusanja je pala — vrati UI u iskljuceno stanje (bez polu-otvorenog mikrofona).
            self._stop_listening()
            self._set_status(self.voice_label, "❌ Slušanje je prekinuto — " + str(payload.get("text") or ""), "err")

    def _save_settings_ui(self) -> None:
        self.settings.device_name = self.device_name_edit.text().strip() or self.settings.device_name
        self.settings.mic_device = self.mic_combo.currentData() or ""
        self.settings.stt_mode = self.stt_combo.currentText()
        self.settings.stt_model_size = self.model_size_combo.currentText()
        self.settings.stt_cloud_model = self.cloud_model_combo.currentData() or "whisper-large-v3-turbo"
        self.settings.language = self.lang_combo.currentText()
        trigger_key = self.trigger_key_edit.text().strip()
        if trigger_key:
            try:
                from app.system.hotkey import normalize_hotkey

                trigger_key = normalize_hotkey(trigger_key)
            except ValueError as exc:
                QMessageBox.warning(self, "Trigger taster", f"Neispravan taster: {exc}")
                return
        self.settings.trigger_key = trigger_key
        self.settings.trigger_mode = self.trigger_mode_combo.currentData() or "push_to_talk"
        self.settings.sound_effects = self.sound_check.isChecked()
        self.settings.sensitivity = self.sens_slider.value() / 100.0
        self.settings.listen_only_in_voice = self.only_vc_check.isChecked()
        self.settings.autostart = self.autostart_check.isChecked()
        save_settings(self.paths, self.settings)
        try:
            from app.system.autostart import sync as sync_autostart

            ok, reason = sync_autostart(self.settings.autostart)
            if not ok:
                self.logger.warning("Autostart nije promenjen: %s", reason)
        except Exception as e:
            self.logger.warning("Autostart greška: %s", e)
        self.logger.info("Podešavanja sačuvana.")
        self._set_status(self.command_status, "Podešavanja sačuvana.", "ok")

        # Primeni ODMAH: ako slusanje radi, restartuj ga sa novim podesavanjima
        # (STT model se izbacuje iz RAM-a i ucitava novi).
        if self.listener_service is not None:
            self._restart_listening()

    def _restart_listening(self) -> None:
        """Stopni star servis, oslobodi stari STT model i pokreni novi (bez gašenja checkbox-a)."""
        service = self.listener_service
        self.listener_service = None
        if service is not None:
            # Odmah oslobodi mikrofon i stari model iz RAM-a
            try:
                service.capture.stop()
            except Exception:
                pass
            core = getattr(service, "core", None)
            stt = getattr(core, "stt", None) if core is not None else None
            close = getattr(stt, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
            try:
                self.runner.submit(service.stop())  # cisti loop task u pozadini
            except Exception:
                pass
            self.logger.info("Listening restartovan (nova podešavanja primenjena).")
        self._start_listening()

    # ── Push-to-talk (globalni taster) ───────────────────────────────────────
    def _on_hotkey_pressed(self) -> None:
        self.runner.submit(self._task_hotkey_down())

    def _on_hotkey_released(self) -> None:
        self.runner.submit(self._task_hotkey_up())

    async def _task_hotkey_down(self) -> None:
        core = getattr(self.listener_service, "core", None)
        if core is None:
            return
        mode = getattr(self.settings, "trigger_mode", "push_to_talk") or "push_to_talk"
        if mode == "toggle":
            action = core.toggle()
            if action is None:
                return
            if getattr(action, "kind", "") == "toggle_off":
                self.signals.listener_event.emit({"kind": "ptt_off"})
            else:
                self.signals.listener_event.emit({"kind": "ptt_active"})
        else:
            action = core.trigger_down()
            if action is not None:
                self.signals.listener_event.emit({"kind": "ptt_active"})

    async def _task_hotkey_up(self) -> None:
        core = getattr(self.listener_service, "core", None)
        if core is None:
            return
        if (getattr(self.settings, "trigger_mode", "push_to_talk") or "push_to_talk") != "push_to_talk":
            return
        action = core.trigger_up()
        if action is None or getattr(action, "kind", "") != "utterance":
            return
        result = await core.process_utterance_async(action.audio)
        if result is not None:
            await self._handle_listener_action(result)

    def _apply_hotkey(self) -> None:
        self._remove_hotkey()
        key = (getattr(self.settings, "trigger_key", "") or "").strip()
        if not key:
            return
        try:
            from app.system.hotkey import GlobalHotkey

            self._hotkey = GlobalHotkey(
                on_press=lambda: self.signals.hotkey_pressed.emit(),
                on_release=lambda: self.signals.hotkey_released.emit(),
            )
            self._hotkey.start(key)
            self.logger.info("Globalni taster registrovan: %s", key)
        except Exception as exc:
            self.logger.warning("Globalni taster nije registrovan (%s): %s", key, exc)

    def _remove_hotkey(self) -> None:
        hotkey = getattr(self, "_hotkey", None)
        if hotkey is not None:
            try:
                hotkey.stop()
            except Exception:
                pass
            self._hotkey = None

    def _open_dashboard(self) -> None:
        QDesktopServices.openUrl(QUrl("https://kortikbot.xyz/user/listener"))

    def _unlink_device(self) -> None:
        answer = QMessageBox.question(
            self,
            "Odjava uređaja",
            "Da li da uklonim lokalne kredencijale? Bot će prestati da prihvata komande sa ovog računara.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        self.heartbeat_timer.stop()
        self.access_token = None
        self.token_expires_at = 0.0
        self.flow.unlink()
        self.code_label.setText("——————")
        self.open_dash_btn.setEnabled(False)
        self._set_status(self.conn_status, "Uređaj je odjavljen.", "ok")
        self.stack.setCurrentWidget(self.connect_page)
        self.logger.info("Uređaj odjavljen (lokalni kredencijali obrisani).")

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        try:
            self.heartbeat_timer.stop()
            self._remove_hotkey()
            service, self.listener_service = self.listener_service, None
            if service is not None:
                try:
                    service.capture.stop()
                except Exception:
                    pass
            self.runner.stop()
        except Exception:
            pass
        super().closeEvent(event)

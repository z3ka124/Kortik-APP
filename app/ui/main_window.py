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
    QPlainTextEdit,
    QPushButton,
    QSlider,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.auth.device_flow import DeviceFlow
from app.config import AppPaths, Settings, save_settings
from app.core.parser import parse_command
from app.logs import tail_log
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
QLineEdit, QComboBox, QPlainTextEdit { background: #151922; border: 1px solid #2a3040; border-radius: 8px; padding: 7px; }
QGroupBox { border: 1px solid #2a3040; border-radius: 10px; margin-top: 12px; padding: 12px; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; color: #9aa3b2; }
"""


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

        self.listen_check = QCheckBox("Slušam wake word „Kortik“")
        self.listen_check.setChecked(True)
        self.listen_check.stateChanged.connect(self._on_listen_toggle)
        layout.addWidget(self.listen_check)

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
        self.mic_edit = QLineEdit(self.settings.mic_device)
        self.mic_edit.setPlaceholderText("prazno = sistemski mikrofon")
        form.addRow("Mikrofon", self.mic_edit)
        self.stt_combo = QComboBox()
        self.stt_combo.addItems(["local", "cloud"])
        self.stt_combo.setCurrentText(self.settings.stt_mode)
        form.addRow("STT režim", self.stt_combo)
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["sr", "en", "auto"])
        self.lang_combo.setCurrentText(self.settings.language)
        form.addRow("Jezik komandi", self.lang_combo)
        self.sens_slider = QSlider(Qt.Horizontal)
        self.sens_slider.setRange(0, 100)
        self.sens_slider.setValue(int(round(self.settings.sensitivity * 100)))
        self.sens_slider.setToolTip(
            "Osetljivost wake word-a: levo = strože (manje lažnih poziva), desno = osetljivije"
        )
        form.addRow("Osetljivost wake word-a", self.sens_slider)
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

        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumBlockCount(500)
        log_layout.addWidget(self.log_view)
        refresh_btn = QPushButton("Osveži log")
        refresh_btn.setObjectName("ghost")
        refresh_btn.clicked.connect(self._refresh_log)
        log_layout.addWidget(refresh_btn)
        layout.addWidget(log_box, 1)

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
        return page

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

        if self.settings.listen_only_in_voice:
            self.listen_check.setEnabled(in_voice)
            if not in_voice:
                self.listen_check.setChecked(False)
            elif not self.listen_check.isChecked():
                self.listen_check.setChecked(True)

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

        self._refresh_log()

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

        if not payload.get("signed"):
            self._set_status(
                self.update_label,
                f"Preuzeta verzija {version} nema važeći potpis "
                f"({payload.get('signature_status')}) — neću je instalirati.",
                "err",
            )
            self.logger.error("Update odbijen: Authenticode status=%s", payload.get("signature_status"))
            return

        self._set_status(
            self.update_label,
            f"Verzija {version} je preuzeta i potpisana — spremna za instalaciju.",
            "ok",
        )

        answer = QMessageBox.question(
            self,
            "Ažuriranje spremno",
            f"Verzija {version} je preuzeta i verifikovana.\n\nInstalirati sada? Aplikacija će se zatvoriti.",
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

    def _on_listen_toggle(self, _state: int) -> None:
        if self.listen_check.isChecked():
            self._start_listening()
        else:
            self._stop_listening()

    def _start_listening(self) -> None:
        if self.listener_service is not None:
            return
        try:
            from app.audio.capture import MicrophoneCapture, available as mic_available
            from app.audio.vad import UtteranceRecorder, VadConfig
            from app.core.listener_core import ListenerCore
            from app.core.listener_service import ListenerService
            from app.kws.sherpa_kws import SherpaKws, threshold_from_sensitivity
            from app.stt.base import create_stt

            if not mic_available():
                raise RuntimeError(
                    "Mikrofon nije dostupan (sounddevice / PortAudio nije instaliran)."
                )

            threshold = threshold_from_sensitivity(self.settings.sensitivity)
            kws = SherpaKws(threshold=threshold)
            if not SherpaKws.available(kws.model_dir):
                raise RuntimeError(
                    "Sherpa KWS model „Kortik“ nije pronađen. "
                    f"Očekivana lokacija: {kws.model_dir}"
                )
            kws.load()

            async def _credentials():
                token = await self._ensure_token()
                secret = (self.store.load() or {}).get("device_secret") or ""
                return token, secret

            stt, note = create_stt(
                self.settings.stt_mode,
                self.settings.language,
                api=self.api,
                credentials_provider=_credentials,
            )
            if note:
                self.logger.warning("STT: %s", note)
            if stt is None:
                raise RuntimeError(f"STT nije dostupan: {note}")

            recorder = UtteranceRecorder(VadConfig())
            core = ListenerCore(kws, recorder, stt)
            capture = MicrophoneCapture(device=self.settings.mic_device or None)
            self.listener_service = ListenerService(core, capture, on_action=self._handle_listener_action)
            self.runner.submit(self.listener_service.start())
            self._set_status(
                self.voice_label,
                f"Slušanje: tražim „{self.settings.wake_word}“ (STT={self.settings.stt_mode})",
                "ok",
            )
            self.logger.info(
                "Listening pokrenut (STT=%s, threshold=%.2f)", type(stt).__name__, threshold
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
        self._set_status(self.voice_label, "Slušanje: isključeno", "warn")
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

    def _on_listener_event(self, payload: dict) -> None:
        kind = (payload or {}).get("kind")
        if kind == "wake":
            self._set_status(self.voice_label, f"👂 Čuo sam „{payload.get('keyword')}“ — govori…", "ok")
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

    def _refresh_log(self) -> None:
        try:
            self.log_view.setPlainText(tail_log(self.paths.logs, 60))
            self.log_view.verticalScrollBar().setValue(self.log_view.verticalScrollBar().maximum())
        except Exception:
            pass

    def _save_settings_ui(self) -> None:
        save_settings(self.paths, self.settings)
        self.settings.device_name = self.device_name_edit.text().strip() or self.settings.device_name
        self.settings.mic_device = self.mic_edit.text().strip()
        self.settings.stt_mode = self.stt_combo.currentText()
        self.settings.language = self.lang_combo.currentText()
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
        self._set_status(self.command_status, "Podešavanja su sačuvana.", "ok")

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

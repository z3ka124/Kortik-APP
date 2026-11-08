# c:\Kortik\Kortik-Listener-App\app\system\autostart.py
"""
Autostart preko `HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`.

Namerno per-user (HKCU), bez admin prava i bez Scheduled Task-ova.
Na ne-Windows platformama funkcije su no-op.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Tuple

logger = logging.getLogger("kortik.listener.autostart")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "KortikListener"

_IS_WINDOWS = sys.platform.startswith("win")


def _winreg():
    import winreg  # lokalni import da modul radi i van Windows-a

    return winreg


def default_command() -> str:
    """Komanda koja se upisuje u registry."""
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable).resolve()}"'

    pythonw = Path(sys.executable).with_name("pythonw.exe")
    interpreter = pythonw if pythonw.exists() else Path(sys.executable)
    return f'"{interpreter}" -m app.main'


def is_enabled() -> bool:
    if not _IS_WINDOWS:
        return False
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _type = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(str(value).strip())
    except FileNotFoundError:
        return False
    except OSError as e:
        logger.debug("Autostart read greška: %s", e)
        return False


def enable(command: str | None = None) -> Tuple[bool, str]:
    if not _IS_WINDOWS:
        return False, "Autostart je podržan samo na Windows-u."
    winreg = _winreg()
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, command or default_command())
        logger.info("Autostart uključen.")
        return True, "ok"
    except OSError as e:
        logger.warning("Autostart enable greška: %s", e)
        return False, str(e)


def disable() -> Tuple[bool, str]:
    if not _IS_WINDOWS:
        return False, "Autostart je podržan samo na Windows-u."
    winreg = _winreg()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, VALUE_NAME)
        logger.info("Autostart isključen.")
        return True, "ok"
    except FileNotFoundError:
        return True, "already_disabled"
    except OSError as e:
        logger.warning("Autostart disable greška: %s", e)
        return False, str(e)


def sync(enabled: bool) -> Tuple[bool, str]:
    """Uskladi registry sa zeljenim stanjem (idempotentno)."""
    if enabled:
        return enable()
    return disable()

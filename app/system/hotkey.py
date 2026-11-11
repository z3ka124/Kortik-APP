# c:\Kortik\Kortik-Listener-App\app\system\hotkey.py
"""Globalni Windows hotkey (RegisterHotKey) za push-to-talk okidač.

Nema spoljnih zavisnosti — koristi ctypes/user32. Registracija i message pump
idu u poseban thread; `callback` se poziva na tom threadu (MainWindow ga
premošćuje na Qt signal).
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable, Optional, Tuple

MOD_ALT = 0x1
MOD_CONTROL = 0x2
MOD_SHIFT = 0x4

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

_VK: dict = {}
for _i, _ch in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ"):
    _VK[_ch] = 0x41 + _i
for _i in range(10):
    _VK[str(_i)] = 0x30 + _i
for _i in range(1, 25):
    _VK[f"F{_i}"] = 0x70 + (_i - 1)
_VK.update(
    {
        "SPACE": 0x20, "SPACEBAR": 0x20,
        "ESC": 0x1B, "ESCAPE": 0x1B,
        "ENTER": 0x0D, "RETURN": 0x0D,
        "TAB": 0x09,
        "PRINTSCREEN": 0x2C, "PRTSC": 0x2C,
        "PAUSE": 0x13,
        "DELETE": 0x2E, "DEL": 0x2E,
        "END": 0x23, "HOME": 0x24, "PGUP": 0x21, "PGDN": 0x22,
    }
)


def parse_hotkey(text: str) -> Tuple[int, int]:
    """Vraća (modifieri, virtual_key). Baca ValueError za neispravan tekst."""
    raw = (text or "").strip()
    if not raw:
        raise ValueError("prazan taster")
    parts = [p.strip() for p in raw.upper().split("+") if p.strip()]
    if not parts:
        raise ValueError("prazan taster")
    mods = 0
    for p in parts[:-1]:
        if p in ("CTRL", "CONTROL"):
            mods |= MOD_CONTROL
        elif p == "ALT":
            mods |= MOD_ALT
        elif p == "SHIFT":
            mods |= MOD_SHIFT
        else:
            raise ValueError(f"nepoznat modifikator: {p}")
    key = parts[-1]
    if key not in _VK:
        raise ValueError(f"nepoznat taster: {key}")
    return mods, _VK[key]


def normalize_hotkey(text: str) -> str:
    """Čitljiv ekran (npr. 'ctrl+k' -> 'CTRL+K'). Baca ValueError ako je neispravno."""
    mods, vk = parse_hotkey(text)
    names = []
    if mods & MOD_CONTROL:
        names.append("CTRL")
    if mods & MOD_ALT:
        names.append("ALT")
    if mods & MOD_SHIFT:
        names.append("SHIFT")
    name: Optional[str] = None
    for candidate, value in _VK.items():
        if value == vk:
            name = candidate
            break
    names.append(name or f"VK{vk}")
    return "+".join(names)


class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", POINT),
    ]


class GlobalHotkey:
    """Registruje globalni taster i poziva callback svaki put kad se pritisne."""

    def __init__(self, callback: Callable[[], None]):
        self._callback = callback
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._id = 0xBEEF
        self._mods = 0
        self._vk = 0
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def start(self, hotkey_text: str) -> None:
        self.stop()
        self._mods, self._vk = parse_hotkey(hotkey_text)
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="kortik-hotkey", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        user32 = ctypes.windll.user32
        try:
            if not user32.RegisterHotKey(None, self._id, self._mods, self._vk):
                self._active = False
                return
            self._active = True
            msg = MSG()
            while not self._stop.is_set():
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result <= 0:  # WM_QUIT ili greška
                    break
                if msg.message == WM_HOTKEY and msg.wParam == self._id:
                    try:
                        self._callback()
                    except Exception:
                        pass
        finally:
            try:
                user32.UnregisterHotKey(None, self._id)
            except Exception:
                pass
            self._active = False

    def stop(self) -> None:
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is None:
            return
        try:
            ctypes.windll.user32.PostThreadMessageW(thread.ident, WM_QUIT, 0, 0)
        except Exception:
            pass
        thread.join(timeout=1.0)
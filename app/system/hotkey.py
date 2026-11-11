# c:\Kortik\Kortik-Listener-App\app\system\hotkey.py
"""Globalni Windows hotkey za push-to-talk (pritisak + otpuštanje tastera).

`RegisterHotKey` daje samo događaj pritiska — nema key-up. Zato koristimo
low-level keyboard hook (WH_KEYBOARD_LL) koji dobija i WM_KEYDOWN i WM_KEYUP,
što je neophodno za pravi "drži taster = snima, pusti = staje" push-to-talk.

Hook radi u POSEBAN thread-u sa sopstvenom message pumpom (GetMessageW) i
obavezno se oslobađa (`UnhookWindowsHookEx`) u `finally`, da ne curi posle
zaustavljanja ili pada aplikacije. Callback (WINFUNCTYPE) se drži u
`self._callback_ref` da ga GC ne pokupi dok je hook aktivan.
"""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes
from typing import Callable, Optional, Tuple

MOD_ALT = 0x1
MOD_CONTROL = 0x2
MOD_SHIFT = 0x4

WM_KEYDOWN = 0x0100
WM_KEYUP = 0x0101
WM_SYSKEYDOWN = 0x0104
WM_SYSKEYUP = 0x0105
WM_QUIT = 0x0012

WH_KEYBOARD_LL = 13
VK_SHIFT = 0x10
VK_CONTROL = 0x11
VK_MENU = 0x12

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
        ("lPrivate", wintypes.DWORD),
    ]


class KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_void_p),
    ]


class GlobalHotkey:
    """Nisko-nivojski keyboard hook: prati pritisak I otpuštanje zadatog tastera."""

    def __init__(
        self,
        on_press: Optional[Callable[[], None]] = None,
        on_release: Optional[Callable[[], None]] = None,
    ):
        self._on_press = on_press
        self._on_release = on_release
        self._thread: Optional[threading.Thread] = None
        self._hook: Optional[int] = None
        self._callback_ref = None
        self._stop = threading.Event()
        self._mods = 0
        self._vk = 0
        self._active = False
        self._down = False

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
        kernel32 = ctypes.windll.kernel32

        def key_down(vk: int) -> bool:
            return bool(user32.GetAsyncKeyState(vk) & 0x8000)

        def mods_match() -> bool:
            ctrl = key_down(VK_CONTROL)
            alt = key_down(VK_MENU)
            shift = key_down(VK_SHIFT)
            return (
                ctrl == bool(self._mods & MOD_CONTROL)
                and alt == bool(self._mods & MOD_ALT)
                and shift == bool(self._mods & MOD_SHIFT)
            )

        HOOKPROC = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM
        )

        def _hook_proc(nCode, wParam, lParam):
            try:
                if nCode >= 0:
                    msg = int(wParam)
                    if msg in (WM_KEYDOWN, WM_SYSKEYDOWN):
                        kbd = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                        if kbd.vkCode == self._vk and mods_match():
                            if not self._down:
                                self._down = True
                                if self._on_press:
                                    try:
                                        self._on_press()
                                    except Exception:
                                        pass
                    elif msg in (WM_KEYUP, WM_SYSKEYUP):
                        kbd = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                        if kbd.vkCode == self._vk and self._down:
                            self._down = False
                            if self._on_release:
                                try:
                                    self._on_release()
                                except Exception:
                                    pass
            except Exception:
                pass
            finally:
                return user32.CallNextHookEx(self._hook, nCode, wParam, lParam)

        self._callback_ref = HOOKPROC(_hook_proc)
        hmod = kernel32.GetModuleHandleW(None)
        self._hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._callback_ref, hmod, 0)
        if not self._hook:
            self._active = False
            return
        self._active = True

        msg = MSG()
        try:
            while not self._stop.is_set():
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if result <= 0:  # WM_QUIT ili greška
                    break
        finally:
            if self._hook:
                try:
                    user32.UnhookWindowsHookEx(self._hook)
                except Exception:
                    pass
                self._hook = None
            self._active = False
            self._down = False
            self._callback_ref = None

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
# c:\Kortik\Kortik-Listener-App\app\core\listener_service.py
"""
Async servis koji spaja mikrofon, ListenerCore i slanje komandi.

`on_action` moze biti obicna funkcija ili coroutine; servis je poziva za
svaku akciju (wake / command / text) da UI moze da prikaze sta se desava.
"""
from __future__ import annotations

import asyncio
import inspect
import logging
import time
from typing import Any, Callable, Optional

from app.core.listener_core import ListenerAction, ListenerCore

logger = logging.getLogger("kortik.listener.service")


class ListenerService:
    def __init__(
        self,
        core: ListenerCore,
        capture: Any,
        on_action: Optional[Callable[[ListenerAction], Any]] = None,
        read_timeout: float = 0.5,
        on_level: Optional[Callable[[int], Any]] = None,
        on_error: Optional[Callable[[str], Any]] = None,
    ):
        self.core = core
        self.capture = capture
        self.on_action = on_action
        self.on_level = on_level
        self.on_error = on_error
        self.read_timeout = float(read_timeout)
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._chunks = 0
        self._peak = 0
        self._last_log = time.monotonic()
        self._last_level_emit = 0.0
        self._last_level_value = -1

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if self._running:
            return
        self.capture.start()
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("Listener servis pokrenut.")

    async def stop(self) -> None:
        self._running = False
        task, self._task = self._task, None
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        try:
            self.capture.stop()
        except Exception:
            pass
        logger.info("Listener servis zaustavljen.")

    async def _loop(self) -> None:
        try:
            while self._running:
                chunk = await asyncio.to_thread(self.capture.read, self.read_timeout)
                if not chunk:
                    continue
                await self._handle_chunk(chunk)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Listener petlja prekinuta: %s", e)
            self._running = False
            if self.on_error:
                try:
                    result = self.on_error(str(e))
                    if inspect.isawaitable(result):
                        asyncio.ensure_future(result)
                except Exception:
                    pass

    async def _handle_chunk(self, chunk: bytes) -> None:
        # ── Dijagnostika: da li audio uopste dolazi i koliko je glasan ──────
        self._chunks += 1
        try:
            from app.audio.vad import rms as _rms

            level = int(_rms(chunk))
        except Exception:
            level = 0
        self._peak = max(self._peak, level)

        now = time.monotonic()
        if now - self._last_log >= 5.0:
            logger.info(
                "KWS dijagnostika: %s chunkova u 5s, peak RMS=%s, armed=%s",
                self._chunks,
                self._peak,
                getattr(self.core, "is_armed", None),
            )
            if self._peak < 15:
                logger.warning(
                    "Mikrofon daje skoro tisinu (peak RMS=%s) — proveri izabrani uredjaj "
                    "(SteelSeries Sonar / Sound Mapper znaju biti nemi).",
                    self._peak,
                )
            self._chunks = 0
            self._peak = 0
            self._last_log = now

        if self.on_level:
            try:
                level = int(min(100, level / 60))
                # Throttle GUI signal: emit max ~10x/s i samo kad se nivo promeni
                # (inace 50 Qt signala/s bez potrebe trosi CPU i moze smetati).
                now_l = time.monotonic()
                if level != self._last_level_value and now_l - self._last_level_emit >= 0.1:
                    self._last_level_emit = now_l
                    self._last_level_value = level
                    self.on_level(level)
            except Exception:
                pass

        action = self.core.process_chunk(chunk)
        if not action:
            return

        await self._emit(action)

        if action.kind == "utterance":
            result = await self.core.process_utterance_async(action.audio)
            if result:
                await self._emit(result)

    async def _emit(self, action: ListenerAction) -> None:
        if not self.on_action:
            return
        try:
            result = self.on_action(action)
            if inspect.isawaitable(result):
                await result
        except Exception as e:
            logger.warning("on_action greška: %s", e)

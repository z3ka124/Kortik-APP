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
    ):
        self.core = core
        self.capture = capture
        self.on_action = on_action
        self.read_timeout = float(read_timeout)
        self._running = False
        self._task: Optional[asyncio.Task] = None

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

    async def _handle_chunk(self, chunk: bytes) -> None:
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

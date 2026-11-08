# c:\Kortik\Kortik-Listener-App\app\ui\async_runner.py
"""
Asyncio event loop u pozadinskom threadu.

Qt event loop ostaje responzivan; mreza i STT rade u ovom loop-u.
Sve sto treba da dodirne widget-e ide preko Qt signala (thread-safe emit).
"""
from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Coroutine, Optional


class AsyncRunner:
    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, name="kortik-async", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            try:
                self._loop.close()
            except Exception:
                pass

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    def submit(self, coro: Coroutine[Any, Any, Any]) -> Future:
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    def stop(self, timeout: float = 3.0) -> None:
        if self._loop.is_closed():
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=timeout)


def safe_result(future: Future) -> Optional[Any]:
    """Pomocna funkcija za dijagnostiku — nikad ne baca."""
    try:
        return future.result(timeout=0.01)
    except Exception:
        return None

# c:\Kortik\Kortik-Listener-App\app\core\listener_core.py
"""
Orkestracija: wake word -> snimak komande -> STT -> parser.

Sve je sinhrono i bez ijedne spoljne zavisnosti (KWS, recorder i STT se
ubacuju), pa se lako testira bez mikrofona i bez modela.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any, Optional

from app.core.parser import has_wake_word, is_wake_word_only, parse_command, split_wake_word

logger = logging.getLogger("kortik.listener.core")


@dataclass
class ListenerAction:
    kind: str                 # wake | utterance | wake_only | command | text
    keyword: str = ""
    text: str = ""
    command: str = ""
    query: str = ""
    audio: bytes = b""


class ListenerCore:
    def __init__(
        self,
        kws: Any,
        recorder: Any,
        stt: Optional[Any] = None,
        cooldown_seconds: float = 1.2,
        clock=time.monotonic,
        wake_by_stt: bool = False,
        followup_seconds: float = 6.0,
    ):
        self.kws = kws
        self.recorder = recorder
        self.stt = stt
        self.cooldown_seconds = float(cooldown_seconds)
        self.clock = clock
        self.wake_by_stt = bool(wake_by_stt)
        self.followup_seconds = float(followup_seconds)

        self._armed = False
        self._last_wake = 0.0
        self._followup_until = 0.0

    @property
    def is_armed(self) -> bool:
        return self._armed

    def reset(self) -> None:
        self._armed = False
        try:
            self.recorder.reset()
        except Exception:
            pass
        reset = getattr(self.kws, "reset", None)
        if callable(reset):
            try:
                reset()
            except Exception:
                pass

    def trigger(self, now: Optional[float] = None) -> Optional[ListenerAction]:
        """Ručni okidač (push-to-talk): isto kao da je izgovoren wake word.

        Sledeći audio chunk ulazi direktno u utterance snimanje (bez KWS-a).
        """
        if self.wake_by_stt:
            return None
        current = self.clock() if now is None else now
        self._last_wake = current
        self._armed = True
        try:
            self.recorder.reset()
        except Exception:
            pass
        logger.info("Ručni okidač (PTT taster).")
        return ListenerAction(kind="wake", keyword="trigger")

    # ── obrada 20 ms chunkova ───────────────────────────────────────────────
    def process_chunk(self, pcm: bytes, now: Optional[float] = None) -> Optional[ListenerAction]:
        if not pcm:
            return None

        current = self.clock() if now is None else now

        # ── Rezim "wake by STT": nema KWS-a, snimamo svaki izgovor i tek posle
        #    transkripcije proveravamo da li sadrzi "Kortik" (radi na srpskom).
        if self.wake_by_stt:
            audio = self.recorder.feed(pcm)
            if audio:
                return ListenerAction(kind="utterance", audio=audio)
            return None

        # Nakon wake word-a: snimamo dok VAD ne zavrsi izgovor
        if self._armed:
            audio = self.recorder.feed(pcm)
            if audio:
                self._armed = False
                return ListenerAction(kind="utterance", audio=audio)
            return None

        if current - self._last_wake < self.cooldown_seconds:
            return None

        keyword = self._detect_keyword(pcm)
        if not keyword:
            return None

        self._last_wake = current
        self._armed = True
        try:
            self.recorder.reset()
        except Exception:
            pass
        logger.info("Wake word: %s", keyword)
        return ListenerAction(kind="wake", keyword=str(keyword))

    def _detect_keyword(self, pcm: bytes) -> Optional[str]:
        process = getattr(self.kws, "process", None)
        if callable(process):
            try:
                return process(pcm)
            except Exception as e:
                logger.warning("KWS greška: %s", e)
                return None
        check = getattr(self.kws, "check", None)
        if callable(check):
            try:
                return check(0, pcm)
            except Exception as e:
                logger.warning("KWS greška: %s", e)
        return None

    # ── obrada snimljenog izgovora (blokirajuce — zovi iz thread-a) ─────────
    def process_utterance(self, audio: bytes) -> Optional[ListenerAction]:
        if not audio or self.stt is None:
            return None
        try:
            text = (self.stt.transcribe(audio) or "").strip()
        except Exception as e:
            logger.warning("STT greška: %s", e)
            return None
        return self.parse_text(text)

    async def process_utterance_async(self, audio: bytes) -> Optional[ListenerAction]:
        """Koristi async STT (cloud) kada je dostupan, inace lokalni u thread-u."""
        import asyncio

        if not audio or self.stt is None:
            return None

        transcribe_async = getattr(self.stt, "transcribe_async", None)
        if callable(transcribe_async):
            try:
                text = (await transcribe_async(audio) or "").strip()
            except Exception as e:
                logger.warning("Cloud STT greška: %s", e)
                return None
            return self.parse_text(text)

        return await asyncio.to_thread(self.process_utterance, audio)

    def parse_text(self, text: str) -> Optional[ListenerAction]:
        return self._handle_text(text)

    def _handle_text(self, text: str) -> Optional[ListenerAction]:
        text = (text or "").strip()
        if not text:
            return None

        if self.wake_by_stt:
            remainder, had_wake = split_wake_word(text)
            now = self.clock()
            if had_wake:
                remainder = (remainder or "").strip()
                if not remainder:
                    self._followup_until = now + self.followup_seconds
                    return ListenerAction(kind="wake_only", text=text)
                self._followup_until = 0.0
                parsed = parse_command(remainder)
                if parsed:
                    return ListenerAction(kind="command", text=text, command=parsed[0], query=parsed[1])
                return ListenerAction(kind="text", text=text)

            # Prozor posle samog "Kortik" — sledeci izgovor je komanda
            if now < self._followup_until:
                self._followup_until = 0.0
                parsed = parse_command(text)
                if parsed:
                    return ListenerAction(kind="command", text=text, command=parsed[0], query=parsed[1])
            return None

        # Klasican KWS rezim
        if is_wake_word_only(text):
            return ListenerAction(kind="wake_only", text=text)

        parsed = parse_command(text)
        if parsed:
            return ListenerAction(kind="command", text=text, command=parsed[0], query=parsed[1])

        return ListenerAction(kind="text", text=text)

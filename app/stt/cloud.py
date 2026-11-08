# c:\Kortik\Kortik-Listener-App\app\stt\cloud.py
"""
Cloud STT — komanda se šalje na Kortik backend, koji je prosleđuje Groq Whisper-u.

Koristi se samo ako korisnik eksplicitno izabere „cloud“ režim, jer audio
tada napušta računar. Zahtev je HMAC-potpisan i ograničen na 12 s / ~1.2 MB.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional, Tuple

from app.stt.wav import pcm_to_wav

logger = logging.getLogger("kortik.listener.stt.cloud")

CredentialsProvider = Callable[[], Awaitable[Tuple[str, str]]]


class CloudSpeechToText:
    def __init__(
        self,
        api: Any,
        credentials_provider: Optional[CredentialsProvider] = None,
        language: str = "sr",
    ):
        self.api = api
        self.credentials_provider = credentials_provider
        self.language = language or "sr"

    def available(self) -> bool:
        return self.api is not None and callable(self.credentials_provider)

    def transcribe(self, pcm: bytes, sample_rate: int = 16000) -> str:
        raise RuntimeError("Cloud STT je asinhron — koristi transcribe_async().")

    async def transcribe_async(self, pcm: bytes, sample_rate: int = 16000) -> str:
        if not self.available():
            raise RuntimeError("Cloud STT nije konfigurisan (nedostaje API ili sesija).")
        if not pcm:
            return ""

        token, device_secret = await self.credentials_provider()  # type: ignore[misc]
        wav_bytes = pcm_to_wav(pcm, sample_rate)

        result = await self.api.transcribe_audio(
            access_token=token,
            device_secret=device_secret,
            wav_bytes=wav_bytes,
            language=self.language,
        )
        status = str(result.get("status") or "")
        if status != "success":
            logger.warning("Cloud STT nije uspeo: %s", result)
            return ""
        return str(result.get("text") or "").strip()

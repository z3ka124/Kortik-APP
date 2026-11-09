# c:\Kortik\Kortik-Listener-App\app\stt\base.py
"""
STT interfejs + factory za hibridni rezim (local / cloud).

`local`  = faster-whisper na uredjaju (audio ne izlazi sa računara) — default
`cloud`  = backend proxy ka Groq Whisper-u (audio se salje; M4 faza)

Ako izabrani rezim nije dostupan, factory se **vraca na lokalni** i vrati
razlog, da UI moze da obavesti korisnika.
"""
from __future__ import annotations

import logging
from typing import Optional, Protocol, Tuple

logger = logging.getLogger("kortik.listener.stt")


class SpeechToText(Protocol):
    def available(self) -> bool:  # pragma: no cover - interface
        ...

    def transcribe(self, pcm: bytes, sample_rate: int = 16000) -> str:  # pragma: no cover
        ...


def create_stt(
    mode: str,
    language: str = "sr",
    model_size: str = "small",
    api: Any = None,
    credentials_provider: Any = None,
    cloud_model: str = "whisper-large-v3-turbo",
) -> Tuple[Optional[SpeechToText], str]:
    """
    Vraca (engine, napomena). `engine` je None samo ako ni lokalni nije moguc.
    """
    from app.stt.cloud import CloudSpeechToText
    from app.stt.local_whisper import LocalWhisper

    normalized = (mode or "local").strip().lower()
    note = ""

    if normalized == "cloud":
        cloud = CloudSpeechToText(
            api=api,
            credentials_provider=credentials_provider,
            language=language,
            model=cloud_model,
        )
        if cloud.available():
            return cloud, "cloud"
        note = "Cloud STT nije dostupan (nema sesije) — prebacujem na lokalni model."

    local = LocalWhisper(model_size=model_size, language=language)
    if not local.available():
        return None, note or "Lokalni STT nije instaliran (pip install faster-whisper)."

    return local, note

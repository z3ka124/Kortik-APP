# c:\Kortik\Kortik-Listener-App\app\stt\local_whisper.py
"""
Lokalni STT preko `faster-whisper` (CTranslate2, CPU int8).

Audio nikad ne napušta računar. Model se učitava lenjo (prvi prepoznati
izgovor plaća ~1-2 s), a posle ostaje u memoriji.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("kortik.listener.stt.local")

DEFAULT_MODEL_SIZE = "small"
SUPPORTED_SIZES = ("tiny", "base", "small", "medium")


def pcm16_to_float(pcm: bytes):
    """int16 PCM -> float32 numpy ndarray u [-1, 1].

    MORA biti np.ndarray: faster-whisper prihvata `np.ndarray` direktno kao već
    dekodovan audio, a ako dobije Python listu/bytes, pokusa da ga otvori kao
    fajl preko PyAV (`av.open(..., metadata_errors=...)`) -> `UnicodeEncodeError`/
    `metadata_errors` greska i STT uvek vrati prazno.
    """
    import numpy as np

    data = np.frombuffer(pcm[: len(pcm) - (len(pcm) % 2)], dtype=np.int16)
    return (data.astype(np.float32) / 32768.0)


class LocalWhisper:
    def __init__(
        self,
        model_size: str = DEFAULT_MODEL_SIZE,
        language: str = "sr",
        compute_type: str = "int8",
        beam_size: int = 1,
        download_root: Optional[Path] = None,
        ncpu: int = 4,
    ):
        self.model_size = model_size if model_size in SUPPORTED_SIZES else DEFAULT_MODEL_SIZE
        self.language = language or "sr"
        self.compute_type = compute_type
        self.beam_size = int(beam_size)
        self.download_root = Path(download_root) if download_root else None
        self._model = None
        self.ncpu = int(ncpu or 1)

    @staticmethod
    def available() -> bool:
        try:
            import faster_whisper  # noqa: F401

            return True
        except Exception:
            return False

    def load(self) -> "LocalWhisper":
        if self._model is not None:
            return self
        from faster_whisper import WhisperModel

        logger.info("Učitavam faster-whisper model '%s' (%s)…", self.model_size, self.compute_type)
        kwargs = {
            "device": "cpu",
            "compute_type": self.compute_type,
            "cpu_threads": self.ncpu,
        }
        if self.download_root:
            kwargs["download_root"] = str(self.download_root)
        self._model = WhisperModel(self.model_size, **kwargs)
        logger.info("faster-whisper model spreman.")
        return self

    def close(self) -> None:
        """Oslobadja model iz RAM-a (koristi se kad korisnik promeni model)."""
        self._model = None

    def transcribe(self, pcm: bytes, sample_rate: int = 16000) -> str:
        if not pcm:
            return ""
        self.load()

        audio = pcm16_to_float(pcm)
        try:
            segments, _info = self._model.transcribe(
                audio,
                language=None if self.language in ("auto", "") else self.language,
                beam_size=self.beam_size,
                vad_filter=False,
                condition_on_previous_text=False,
            )
            return " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as e:
            logger.warning("faster-whisper greška: %s", e)
            return ""

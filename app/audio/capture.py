# c:\Kortik\Kortik-Listener-App\app\audio\capture.py
"""
Snimanje mikrofona preko `sounddevice` (16 kHz, mono, 20 ms chunkovi).

Ako sounddevice/PortAudio nisu dostupni, `available()` vraca False i UI to
prikaze — aplikacija ostaje upotrebljiva (login, status, test komanda).
"""
from __future__ import annotations

import logging
import queue
from typing import Any, Dict, List, Optional

logger = logging.getLogger("kortik.listener.capture")

SAMPLE_RATE = 16000
BLOCK_SAMPLES = 320          # 20 ms
BLOCK_BYTES = BLOCK_SAMPLES * 2
CHANNELS = 1
DTYPE = "int16"

try:  # pragma: no cover - platformski kod
    import sounddevice as sd
except Exception:  # ImportError ili PortAudio problem
    sd = None
    logger.warning("sounddevice nije dostupan — snimanje mikrofona je onemogućeno.")


def available() -> bool:
    return sd is not None


def list_input_devices() -> List[Dict[str, Any]]:
    if sd is None:
        return []
    try:
        devices = sd.query_devices()
        result = []
        for index, device in enumerate(devices):
            if int(device.get("max_input_channels") or 0) > 0:
                result.append(
                    {
                        "index": index,
                        "name": str(device.get("name") or f"Input {index}"),
                        "channels": int(device.get("max_input_channels") or 0),
                        "default_samplerate": float(device.get("default_samplerate") or 0),
                    }
                )
        return result
    except Exception as e:
        logger.warning("Ne mogu da izlistam mikrofone: %s", e)
        return []


def resolve_device(device: Optional[str]) -> Optional[int]:
    """Ime uredjaja -> indeks. Nepoznato ime vraca None (sistemski default)."""
    if not device:
        return None
    if str(device).isdigit():
        return int(device)
    needle = str(device).strip().lower()
    for item in list_input_devices():
        if needle in item["name"].lower():
            return int(item["index"])
    return None


class MicrophoneCapture:
    """Thread-safe: PortAudio callback samo puni queue, obrada je izvan njega."""

    def __init__(
        self,
        device: Optional[str] = None,
        sample_rate: int = SAMPLE_RATE,
        max_queue: int = 400,
    ):
        self.device_name = device
        self.sample_rate = int(sample_rate)
        self.queue: "queue.Queue[bytes]" = queue.Queue(maxsize=max_queue)
        self._stream = None
        self._dropped = 0

    def is_running(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if sd is None:
            raise RuntimeError("sounddevice nije instaliran — ne mogu da snimam mikrofon.")
        if self._stream is not None:
            return

        index = resolve_device(self.device_name)
        try:
            self._stream = sd.InputStream(
                device=index,
                samplerate=self.sample_rate,
                blocksize=BLOCK_SAMPLES,
                channels=CHANNELS,
                dtype=DTYPE,
                callback=self._callback,
            )
            self._stream.start()
            logger.info(
                "Mikrofon pokrenut (device=%s, rate=%s)", index if index is not None else "default", self.sample_rate
            )
        except Exception as e:
            self._stream = None
            raise RuntimeError(f"Ne mogu da otvorim mikrofon: {e}") from e

    def stop(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
            logger.info("Mikrofon zaustavljen.")

    def read(self, timeout: float = 1.0) -> Optional[bytes]:
        """Blokirajuce uzimanje jednog chunk-a (poziva se iz worker thread-a)."""
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def _callback(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:  # noqa: ARG002
        try:
            if status:
                logger.debug("PortAudio status: %s", status)
            self.queue.put_nowait(bytes(indata))
        except queue.Full:
            self._dropped += 1
            if self._dropped % 100 == 1:
                logger.warning("Audio queue pun — preskačem chunk (ukupno %s)", self._dropped)
        except Exception:
            pass

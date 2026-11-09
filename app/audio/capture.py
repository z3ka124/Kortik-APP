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
    """Thread-safe: PortAudio callback samo puni queue, obrada je izvan njega.

    Vazno: uredjaj se otvara u NJEGOVOJ nativnoj frekvenciji (npr. 48000 Hz) i
    onda se resample-uje na 16 kHz. Ako se WASAPI uredjaj otvori direktno na
    16 kHz, neki drajveri vracaju tišinu (RMS ~0-10) iako mikrofon radi.
    """

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
        self._native_rate = self.sample_rate
        self._channels = CHANNELS
        self.device_label = "default"

    def is_running(self) -> bool:
        return self._stream is not None

    def start(self) -> None:
        if sd is None:
            raise RuntimeError("sounddevice nije instaliran — ne mogu da snimam mikrofon.")
        if self._stream is not None:
            return

        index = resolve_device(self.device_name)
        try:
            info = sd.query_devices(index) if index is not None else sd.query_devices(kind="input")
            native = int(round(float(info.get("default_samplerate") or self.sample_rate)))
            max_inputs = int(info.get("max_input_channels") or 1)
            label = str(info.get("name") or "default")
        except Exception:
            native, max_inputs, label = self.sample_rate, 1, "default"

        if native < 8000:
            native = self.sample_rate
        channels = 1 if max_inputs >= 1 else 2
        attempts = [
            (native, channels),
            (native, 2),
            (self.sample_rate, 1),
            (self.sample_rate, 2),
        ]

        last_error = None
        for rate, chans in attempts:
            if rate <= 0:
                continue
            try:
                stream = sd.InputStream(
                    device=index,
                    samplerate=rate,
                    blocksize=max(160, int(rate * BLOCK_SAMPLES / SAMPLE_RATE)),
                    channels=chans,
                    dtype=DTYPE,
                    callback=self._callback,
                )
                stream.start()
                self._stream = stream
                self._native_rate = rate
                self._channels = chans
                self.device_label = label
                logger.info(
                    "Mikrofon pokrenut (device=%s '%s', native=%s Hz → %s Hz, channels=%s)",
                    index if index is not None else "default",
                    label,
                    rate,
                    self.sample_rate,
                    chans,
                )
                return
            except Exception as exc:
                last_error = exc
                logger.debug("Mikrofon open %s Hz/%s ch nije uspeo: %s", rate, chans, exc)

        self._stream = None
        raise RuntimeError(f"Ne mogu da otvorim mikrofon: {last_error}")

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
            data = bytes(indata)
            if self._channels == 2:
                data = downmix_stereo(data)
            if self._native_rate != self.sample_rate:
                data = resample_int16(data, self._native_rate, self.sample_rate)
            if data:
                self.queue.put_nowait(data)
        except queue.Full:
            self._dropped += 1
            if self._dropped % 100 == 1:
                logger.warning("Audio queue pun — preskačem chunk (ukupno %s)", self._dropped)
        except Exception:
            pass


def downmix_stereo(pcm: bytes) -> bytes:
    """Stereo int16 -> mono int16."""
    try:
        import numpy as np

        data = np.frombuffer(pcm, dtype=np.int16)
        if data.size % 2:
            data = data[:-1]
        mono = data.reshape(-1, 2).mean(axis=1)
        return mono.astype(np.int16).tobytes()
    except Exception:
        return pcm[0::4] + pcm[1::4]


def resample_int16(pcm: bytes, src_rate: int, dst_rate: int) -> bytes:
    """Linearna interpolacija int16 PCM-a (dovoljno za KWS/VAD)."""
    if src_rate == dst_rate or not pcm:
        return pcm
    try:
        import numpy as np

        data = np.frombuffer(pcm, dtype=np.int16)
        if data.size == 0:
            return b""
        count = int(round(data.size * dst_rate / src_rate))
        if count <= 0:
            return b""
        positions = np.linspace(0, data.size - 1, count)
        out = np.interp(positions, np.arange(data.size), data.astype(np.float32))
        return out.astype(np.int16).tobytes()
    except Exception:
        return pcm

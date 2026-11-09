# c:\Kortik\Kortik-Listener-App\app\kws\openwakeword_kws.py
"""
OpenWakeWord wake word detektor za frazu „Hey Jarvis“ (hey_jarvis model).

Interfejs je isti kao sto je bio SherpaKws (`available()/load()/process()/
reset()/close()`), pa `ListenerCore` ne mora da zna koji engine je aktivan.

Model je bundled u `models/openwakeword/` (hey_jarvis_v0.1.onnx + melspectrogram
i embedding — sve iz pip paketa `openwakeword`, Apache-2.0). Nema poziva na mrezu
u runtime-u.

OpenWakeWord radi sa onnxruntime (vec instaliran) i trosi ~0.1-0.3% CPU-a.
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("kortik.listener.kws.oww")

SAMPLE_RATE = 16000
FRAME_SAMPLES = 1280            # 80 ms @ 16 kHz
FRAME_BYTES = FRAME_SAMPLES * 2
WAKE_LABEL = "hey_jarvis"
_MODEL_FILES = ("hey_jarvis_v0.1.onnx", "melspectrogram.onnx", "embedding_model.onnx")


def _bundle_root() -> Optional[Path]:
    """Koren bundle-a kada se app vrti kao PyInstaller .exe."""
    if not getattr(sys, "frozen", False):
        return None
    base = getattr(sys, "_MEIPASS", None)
    return Path(base) if base else Path(sys.executable).resolve().parent


def default_model_dir() -> Path:
    """Traži model u bundle-u, pa u repou, pa u app-data folderu."""
    bundle = _bundle_root()
    if bundle is not None:
        bundled = bundle / "models" / "openwakeword"
        if (bundled / "hey_jarvis_v0.1.onnx").exists():
            return bundled

    here = Path(__file__).resolve()
    repo_candidate = here.parents[2] / "models" / "openwakeword"
    if (repo_candidate / "hey_jarvis_v0.1.onnx").exists():
        return repo_candidate

    base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Kortik" / "Listener" / "models" / "openwakeword"


def threshold_from_sensitivity(sensitivity: float) -> float:
    """
    0.0 (strogo, malo lažnih pozitiva) .. 1.0 (osetljivo, hvata i tih govor).

    OpenWakeWord „hey_jarvis" realno govor daje ~0.70-0.99, lažni okidači
    < 0.30 — mapiramo 0..1 na 0.75..0.30.
    """
    value = min(1.0, max(0.0, float(sensitivity)))
    return round(0.75 - 0.45 * value, 3)


class OpenWakeWordKws:
    def __init__(
        self,
        model_dir: Optional[Path] = None,
        threshold: float = 0.45,
        num_threads: int = 2,
    ):
        self.model_dir = Path(model_dir) if model_dir else default_model_dir()
        self.threshold = float(threshold)
        self.num_threads = int(num_threads)
        self._model = None
        self._buf = bytearray()

    # ── dostupnost ──────────────────────────────────────────────────────────
    @classmethod
    def available(cls, model_dir: Optional[Path] = None) -> bool:
        try:
            import openwakeword  # noqa: F401
            import onnxruntime  # noqa: F401
        except Exception:
            return False
        target = Path(model_dir) if model_dir else default_model_dir()
        return all((target / name).exists() for name in _MODEL_FILES)

    # ── zivotni ciklus ──────────────────────────────────────────────────────
    def load(self) -> "OpenWakeWordKws":
        if self._model is not None:
            return self

        if not self.available(self.model_dir):
            raise FileNotFoundError(
                f"OpenWakeWord model nije kompletan u {self.model_dir}"
            )

        import numpy as np
        from openwakeword.model import Model

        self._model = Model(
            wakeword_models=[str(self.model_dir / "hey_jarvis_v0.1.onnx")],
            inference_framework="onnx",
            melspec_model_path=str(self.model_dir / "melspectrogram.onnx"),
            embedding_model_path=str(self.model_dir / "embedding_model.onnx"),
            ncpu=1,
        )
        # Pre-warm: OpenWakeWord vraca 0.0 prvih 5 frejmova — hranimo tisinu
        # da ne „pojede" pocetak prve reci „Hey".
        self._model.predict(np.zeros(FRAME_SAMPLES * 5, dtype=np.int16))
        logger.info(
            "OpenWakeWord spreman (threshold=%.2f, model=hey_jarvis)", self.threshold
        )
        return self

    def reset(self) -> None:
        self._buf = bytearray()
        if self._model is None:
            return
        try:
            import numpy as np

            self._model.reset()
            self._model.predict(np.zeros(FRAME_SAMPLES * 5, dtype=np.int16))
        except Exception as e:  # pragma: no cover - odbrana od C++ izuzetaka
            logger.debug("OpenWakeWord reset greška: %s", e)

    def close(self) -> None:
        self._model = None
        self._buf = bytearray()

    def peak_score(self, pcm_16k_mono: bytes) -> float:
        """Max skor nad celim baferom (za dijagnostiku) — bez trigger logike."""
        if self._model is None or not pcm_16k_mono:
            return 0.0
        best = 0.0
        try:
            import numpy as np

            for offset in range(0, len(pcm_16k_mono) - FRAME_BYTES + 1, FRAME_BYTES):
                frame = pcm_16k_mono[offset:offset + FRAME_BYTES]
                scores = self._model.predict(np.frombuffer(frame, dtype=np.int16))
                if isinstance(scores, dict) and scores:
                    best = max(best, max(float(v) for v in scores.values()))
        except Exception as e:  # pragma: no cover - odbrana od C++ izuzetaka
            logger.warning("OpenWakeWord score greška: %s", e)
        return best

    # ── obrada ──────────────────────────────────────────────────────────────
    def process(self, pcm_16k_mono: bytes) -> Optional[str]:
        """Vraca 'hey_jarvis' kad skor prede prag, inace None. Ne baca izuzetke."""
        if self._model is None or not pcm_16k_mono:
            return None

        self._buf += pcm_16k_mono
        best = 0.0
        try:
            import numpy as np

            while len(self._buf) >= FRAME_BYTES:
                frame = bytes(self._buf[:FRAME_BYTES])
                del self._buf[:FRAME_BYTES]
                scores = self._model.predict(np.frombuffer(frame, dtype=np.int16))
                if isinstance(scores, dict) and scores:
                    best = max(best, max(float(v) for v in scores.values()))
        except Exception as e:  # pragma: no cover - odbrana od C++ izuzetaka
            logger.warning("OpenWakeWord greška: %s", e)
            return None

        if best >= self.threshold:
            logger.info("Wake word detektovan: hey_jarvis (skor=%.3f)", best)
            self.reset()
            return WAKE_LABEL
        return None
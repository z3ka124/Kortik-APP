# c:\Kortik\Kortik-Listener-App\app\kws\sherpa_kws.py
"""
Sherpa-ONNX wake word detektor za reč „Kortik“.

Model je već u repou: `Kortik-VoiceListener/models/sherpa-kws` (zipformer, ~12 MB)
i sadrži ključeve `▁K OR TI K` i `▁HE Y ▁K OR TI K` u `keywords.txt`.

Ako sherpa-onnx nije instaliran, `available()` vraća False i aplikacija to
prijavi u UI-ju — nikad ne pada.
"""
from __future__ import annotations

import logging
import os
import sys
from array import array
from pathlib import Path
from typing import Optional

logger = logging.getLogger("kortik.listener.kws")

SAMPLE_RATE = 16000
_MODEL_FILE_PAIRS = (
    ("encoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx", "decoder-epoch-12-avg-2-chunk-16-left-64.int8.onnx", "joiner-epoch-12-avg-2-chunk-16-left-64.int8.onnx"),
    ("encoder-epoch-12-avg-2-chunk-16-left-64.onnx", "decoder-epoch-12-avg-2-chunk-16-left-64.onnx", "joiner-epoch-12-avg-2-chunk-16-left-64.onnx"),
)


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
        bundled = bundle / "models" / "sherpa-kws"
        if bundled.exists():
            return bundled

    here = Path(__file__).resolve()
    repo_candidate = here.parents[3] / "Kortik-VoiceListener" / "models" / "sherpa-kws"
    if repo_candidate.exists():
        return repo_candidate

    base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Kortik" / "Listener" / "models" / "sherpa-kws"


def default_keywords_file() -> Path:
    """
    Nas kalibrisani keyword fajl (bundled uz aplikaciju).

    Zasto ne `models/sherpa-kws/keywords.txt`: taj fajl sadrži i jarvis/alexa
    i prag `#0.08`, što je previše osetljivo i pravi lažne pozive na običan
    razgovor. Ovaj fajl ima samo „Kortik“ varijante sa pragom 0.25-0.32.
    """
    candidates = []
    bundle = _bundle_root()
    if bundle is not None:
        candidates.append(bundle / "app" / "kws" / "keywords_kortik.txt")
        candidates.append(bundle / "kws" / "keywords_kortik.txt")
    candidates.append(Path(__file__).resolve().parent / "keywords_kortik.txt")

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return default_model_dir() / "keywords.txt"


def threshold_from_sensitivity(sensitivity: float) -> float:
    """
    0.0 (strogo, malo lažnih pozitiva) .. 1.0 (osetljivo, hvata i tih govor).

    Sherpa preporučuje 0.25 kao default; mapiramo 0..1 na 0.45..0.10.
    """
    value = min(1.0, max(0.0, float(sensitivity)))
    return round(0.45 - 0.35 * value, 3)


def pcm16_to_float(pcm: bytes) -> list:
    """int16 PCM -> float32 lista u [-1, 1] (bez numpy zavisnosti)."""
    samples = array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    return [s / 32768.0 for s in samples]


class SherpaKws:
    def __init__(
        self,
        model_dir: Optional[Path] = None,
        keywords_file: Optional[Path] = None,
        threshold: float = 0.25,
        score: float = 1.5,
        num_threads: int = 2,
    ):
        self.model_dir = Path(model_dir) if model_dir else default_model_dir()
        self.keywords_file = (
            Path(keywords_file) if keywords_file else default_keywords_file()
        )
        self.threshold = float(threshold)
        self.score = float(score)
        self.num_threads = int(num_threads)

        self._spotter = None
        self._stream = None
        self._sherpa = None

    # ── dostupnost ──────────────────────────────────────────────────────────
    @staticmethod
    def _model_files(model_dir: Path):
        for encoder, decoder, joiner in _MODEL_FILE_PAIRS:
            if (model_dir / encoder).exists() and (model_dir / decoder).exists() and (model_dir / joiner).exists():
                return model_dir / encoder, model_dir / decoder, model_dir / joiner
        return None

    @classmethod
    def available(cls, model_dir: Optional[Path] = None) -> bool:
        try:
            import sherpa_onnx  # noqa: F401
        except ImportError:
            return False
        target = Path(model_dir) if model_dir else default_model_dir()
        if not (target / "tokens.txt").exists():
            return False
        return cls._model_files(target) is not None

    # ── zivotni ciklus ──────────────────────────────────────────────────────
    def load(self) -> "SherpaKws":
        if self._spotter is not None:
            return self

        import sherpa_onnx

        files = self._model_files(self.model_dir)
        if not files:
            raise FileNotFoundError(f"Sherpa KWS model nije kompletan u {self.model_dir}")
        if not self.keywords_file.exists():
            raise FileNotFoundError(f"keywords.txt nije pronađen: {self.keywords_file}")

        encoder, decoder, joiner = files
        self._sherpa = sherpa_onnx
        self._spotter = sherpa_onnx.KeywordSpotter(
            tokens=str(self.model_dir / "tokens.txt"),
            encoder=str(encoder),
            decoder=str(decoder),
            joiner=str(joiner),
            keywords_file=str(self.keywords_file),
            num_threads=self.num_threads,
            keywords_score=self.score,
            keywords_threshold=self.threshold,
            provider="cpu",
        )
        self._stream = self._spotter.create_stream()
        logger.info(
            "Sherpa KWS učitan (threshold=%.2f, model=%s)", self.threshold, self.model_dir.name
        )
        return self

    def reset(self) -> None:
        if self._spotter is None:
            return
        self._stream = self._spotter.create_stream()

    def close(self) -> None:
        self._stream = None
        self._spotter = None

    # ── obrada ──────────────────────────────────────────────────────────────
    def process(self, pcm_16k_mono: bytes) -> Optional[str]:
        """Vraca prepoznatu ključnu reč ili None. Ne baca izuzetke."""
        if self._spotter is None:
            return None
        if not pcm_16k_mono:
            return None

        try:
            samples = pcm16_to_float(pcm_16k_mono)
            self._stream.accept_waveform(SAMPLE_RATE, samples)
            while self._spotter.is_ready(self._stream):
                self._spotter.decode_stream(self._stream)

            result = self._spotter.get_result(self._stream)
            if isinstance(result, str) and result.strip():
                logger.info("Wake word detektovan: %s", result)
                # resetujemo stream da se ista reč ne detektuje više puta
                self._stream = self._spotter.create_stream()
                return result.strip()
        except Exception as e:  # pragma: no cover - odbrana od C++ izuzetaka
            logger.warning("Sherpa KWS greška: %s", e)
            try:
                self._stream = self._spotter.create_stream()
            except Exception:
                pass
        return None

# c:\Kortik\Kortik-Listener-App\app\config.py
"""Putanje i (ne-tajna) podesavanja aplikacije."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict

DEFAULT_WAKE_WORD = "hey jarvis"
DEFAULT_LANGUAGE = "sr"


def app_data_dir() -> Path:
    """%LOCALAPPDATA%\\Kortik\\Listener (ili override preko env-a za testove)."""
    override = os.getenv("KORTIK_LISTENER_HOME", "").strip()
    if override:
        return Path(override)
    base = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(base) / "Kortik" / "Listener"


@dataclass
class AppPaths:
    root: Path
    settings: Path
    secrets: Path
    logs: Path
    updates: Path
    models: Path

    @classmethod
    def build(cls, root: Path | None = None) -> "AppPaths":
        base = Path(root) if root else app_data_dir()
        return cls(
            root=base,
            settings=base / "settings.json",
            secrets=base / "secrets.bin",
            logs=base / "logs",
            updates=base / "updates",
            models=base / "models",
        )

    def ensure(self) -> "AppPaths":
        for folder in (self.root, self.logs, self.updates, self.models):
            folder.mkdir(parents=True, exist_ok=True)
        return self


@dataclass
class Settings:
    """Sve sto NIJE tajna — tajne idu u SecretStore (DPAPI)."""

    # "oww"  = OpenWakeWord akusticni model „hey_jarvis" (brzo, ~0.1-0.3% CPU) — DEFAULT
    # "stt"  = wake word se trazi u transkriptu (Whisper, razume srpski) — fallback
    wake_engine: str = "oww"
    language: str = DEFAULT_LANGUAGE
    stt_mode: str = "local"           # local | cloud
    # Lokalni Whisper model: small (default, najbolje za srpski) | base | tiny
    stt_model_size: str = "small"
    # Cloud (Groq Whisper) model — koristi se samo kad je stt_mode == "cloud".
    # Vrednosti: "whisper-large-v3-turbo" (default, brži) | "whisper-large-v3" (najtačniji).
    stt_cloud_model: str = "whisper-large-v3-turbo"
    mic_device: str = ""              # prazno = sistemski default
    mic_gain: float = 1.0
    sensitivity: float = 0.75          # 0..1 -> prag KWS-a
    # Push-to-talk okidač: tekst tastera ("K", "F9", "CTRL+K"); prazno = isključeno
    trigger_key: str = ""
    # Zvučni efekti (wake word aktiviran + komanda prepoznata)
    sound_effects: bool = True
    listen_only_in_voice: bool = True
    # Da li je korisnik ostavio slusanje upaljeno — pamti se kroz restart
    listening: bool = False
    autostart: bool = False
    start_minimized: bool = False
    # Ako je True, updater odbija installer bez valjanog Authenticode potpisa.
    # Default False: manifest je vec Ed25519-potpisan (sha256 unutra), sto je
    # dovoljna garancija za beta fazu bez EV sertifikata.
    require_authenticode: bool = False
    api_base_url: str = ""
    channel: str = "stable"
    device_name: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Settings":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in (data or {}).items() if k in known})


def load_settings(paths: AppPaths) -> Settings:
    try:
        if paths.settings.exists():
            return Settings.from_dict(json.loads(paths.settings.read_text(encoding="utf-8")))
    except Exception:
        pass
    return Settings()


def save_settings(paths: AppPaths, settings: Settings) -> None:
    paths.ensure()
    tmp = paths.settings.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(paths.settings)

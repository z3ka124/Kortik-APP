# c:\Kortik\Kortik-Listener-App\app\phrases.py
"""
Hvatanje „problematičnih fraza".

Kada STT prepozna govor ali parser NE mapira izgovor u komandu (kind="text"),
ovaj modul cuva frazu lokalno (JSONL, rotirajuci fajl) i drzi poslednjih N fraza
u memoriji da bi mogle da se priloze uz prijavu buga.

Tajne se redaktuju pre upisa (ista logika kao u app.logs.redact).
"""
from __future__ import annotations

import json
import logging
import time
from collections import deque
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.logs import redact

logger = logging.getLogger("kortik.listener.phrases")

MAX_JSONL_BYTES = 512 * 1024   # maks velicina phrases.jsonl pre rotacije
MAX_RECENT = 50                # koliko poslednjih fraza drzimo u memoriji
MIN_TEXT = 2                   # preskoci prekratke/bucne rezultate

_jsonl_path: Optional[Path] = None
_pending: deque = deque(maxlen=MAX_RECENT)


def configure_phrases(log_dir: Path) -> None:
    """Postavi gde se problematične fraze cuvaju (npr. paths.logs)."""
    global _jsonl_path
    _jsonl_path = Path(log_dir) / "phrases.jsonl"


def _clean(value: str, limit: int = 200) -> str:
    return redact(" ".join((value or "").split()))[:limit]


def record_phrase(text: str, *, engine: str = "", language: str = "") -> None:
    """Belezi jednu nerazumevanu frazu. Nikad ne baca."""
    text = _clean(text)
    if not text or len(text) < MIN_TEXT:
        return

    entry: Dict[str, Any] = {
        "ts": time.time(),
        "engine": engine or "",
        "language": language or "",
        "text": text,
    }
    _pending.append(entry)

    if _jsonl_path is None:
        return
    try:
        line = json.dumps(entry, ensure_ascii=False)
        with open(_jsonl_path, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        if _jsonl_path.exists() and _jsonl_path.stat().st_size > MAX_JSONL_BYTES:
            backup = _jsonl_path.with_suffix(".jsonl.1")
            try:
                backup.unlink(missing_ok=True)
                _jsonl_path.replace(backup)
            except Exception:
                pass
    except Exception as e:
        logger.debug("Phrase log greska: %s", e)


def recent_phrases(limit: int = MAX_RECENT) -> List[str]:
    """Poslednjih `limit` fraza (tekstovi) za prilog uz prijavu buga."""
    return [str(e.get("text", "")) for e in list(_pending)[-limit:]]
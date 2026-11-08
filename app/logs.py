# c:\Kortik\Kortik-Listener-App\app\logs.py
"""Rotirajuci logovi sa obaveznom redakcijom tajni."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Pattern, Tuple

_PATTERNS: List[Tuple[Pattern[str], str]] = [
    # Discord bot token (tri segmenta razdvojena tackom)
    (re.compile(r"[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{20,}"), "<redacted-discord-token>"),
    # Authorization: Bearer ...
    (re.compile(r"(Bearer\s+)[A-Za-z0-9._\-]+", re.IGNORECASE), r"\1<redacted>"),
    # token/secret/password polja u JSON-u ili query stringu
    (
        re.compile(
            r"((?:access_token|refresh_token|device_secret|device_code|hmac_secret|secret|password|token)"
            r"\"?\s*[:=]\s*\"?)([^\s\",}&\]]{6,})",
            re.IGNORECASE,
        ),
        r"\1<redacted>",
    ),
]


def redact(text: str) -> str:
    """Uklanja tajne iz bilo kog stringa pre nego sto ode u log/fajl."""
    if not text:
        return ""
    result = str(text)
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    return result


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(record.getMessage())
            record.args = ()
        except Exception:
            record.msg = "<log redaction failed>"
            record.args = ()
        return True


def setup_logging(log_dir: Path, level: int = logging.INFO, name: str = "kortik.listener") -> logging.Logger:
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False

    if logger.handlers:
        return logger

    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        log_dir / "listener.log",
        maxBytes=2 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactingFilter())

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(RedactingFilter())

    logger.addHandler(file_handler)
    logger.addHandler(console)
    return logger


def tail_log(log_dir: Path, lines: int = 80) -> str:
    path = Path(log_dir) / "listener.log"
    if not path.exists():
        return ""
    try:
        content = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""
    return "\n".join(content[-lines:])

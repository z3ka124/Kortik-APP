# c:\Kortik\Kortik-Listener-App\app\core\parser.py
"""
Parser glasovnih komandi (bez ijedne spoljne zavisnosti).

Ulaz:  transkribovani tekst (npr. "Hey Jarvis pusti senidah bez tebe")
Izlaz: (command, query) gde je command jedan od:
       play | skip | stop | pause | resume | volume | autoplay | jump | disconnect | mute | deafen | None

Podržava srpske i engleske fraze. Imena korisnika (kod mute/deafen) se NIKADA
ne normalizuju destruktivno — originalni string (casing i karakteri) ostaje očuvan.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional, Tuple

WAKE_WORDS: Tuple[str, ...] = (
    "hej jarvis", "hey jarvis", "jarvis",
)

STOP_WORDS = {
    "stop", "stani", "stanite", "ugasi", "prekini", "zaustavi", "cuti", "prestani", "dosta",
    "shut up", "halt", "cancel",
}
SKIP_WORDS = {
    "skip", "preskoci", "dalje", "sledeca", "sledecu", "next", "druga", "prebaci", "promeni",
}
PAUSE_WORDS = {"pause", "pauza", "pauziraj", "cekaj", "wait", "pauzu", "hold"}
RESUME_WORDS = {"resume", "nastavi", "unpause", "kreni", "continue", "pusti dalje"}
VOLUME_WORDS = {
    "volume", "volumen", "glasnoca", "glasnocu", "jacina", "pojacaj", "smanji", "utisaj",
    "volume up", "volume down", "turn up", "turn down", "louder", "quieter",
}
PLAY_WORDS = {
    "play", "pusti", "pustaj", "sviraj", "dodaj", "opali", "daj", "ukljuci", "reprodukuj",
    "pokreni", "zapocni", "start", "listen to",
}
AUTOPLAY_WORDS = {"autoplay", "auto plej", "autoplej", "auto play"}
AUTOPLAY_ON_WORDS = {"on", "ukljuci", "upali", "paljenje", "start", "da", "enabled", "ukljucivanje"}
AUTOPLAY_OFF_WORDS = {
    "off", "iskljuci", "ugasi", "gasi", "prekini", "stop", "ne", "disabled",
    "iskljucivanje", "gasenje",
}

DISCONNECT_WORDS = {
    "disconnect", "diskonektuj", "izadji", "napusti", "otkaci se", "idi ca", "leave", "quit",
    "napusti kanal", "leave channel", "disconnect bot",
}

JUMP_PREFIXES = {
    "jump", "jump to", "skoci", "skoci na", "prebaci na", "idi na", "pesma broj", "pesma", "traka broj",
    "traka", "track", "track number", "song number", "broj",
}

MUTE_VERBS = {
    "mute", "mutiraj", "utisi", "ugasi mikrofon", "silence", "mute user",
}

DEAFEN_VERBS = {
    "deafen", "ogluvi", "defenuj", "ugasi zvuk", "zagluvi", "deafen user",
}

_NUMBER_WORDS = {
    "nula": 0, "zero": 0,
    "jedan": 1, "one": 1, "jednu": 1, "prva": 1, "prvu": 1, "first": 1,
    "dva": 2, "two": 2, "dve": 2, "druga": 2, "drugu": 2, "second": 2,
    "tri": 3, "three": 3, "treca": 3, "trecu": 3, "third": 3,
    "cetiri": 4, "four": 4, "fourth": 4,
    "pet": 5, "five": 5, "fifth": 5,
    "sest": 6, "six": 6, "sixth": 6,
    "sedam": 7, "seven": 7, "seventh": 7,
    "osam": 8, "eight": 8, "eighth": 8,
    "devet": 9, "nine": 9, "ninth": 9,
    "deset": 10, "ten": 10, "tenth": 10,
    "jedanaest": 11, "eleven": 11,
    "dvanaest": 12, "twelve": 12,
    "trinaest": 13, "thirteen": 13,
    "cetrnaest": 14, "fourteen": 14,
    "petnaest": 15, "fifteen": 15,
    "dvadeset": 20, "twenty": 20,
    "trideset": 30, "thirty": 30,
    "cetrdeset": 40, "forty": 40,
    "pedeset": 50, "fifty": 50,
    "sezdeset": 60, "sixty": 60,
    "sedamdeset": 70, "seventy": 70,
    "osamdeset": 80, "eighty": 80,
    "devedeset": 90, "ninety": 90,
    "sto": 100, "hundred": 100,
}

_FILLER_WORDS = {
    "molim", "te", "molimte", "bi", "hocu", "zelim", "ajde", "hajde", "sada", "sad",
    "bre", "brate", "mi", "nam", "vam", "moze", "mozes", "please", "can", "you",
}


def normalize(text: str) -> str:
    """Mala slova, bez dijakritika, bez viška razmaka i interpunkcije na krajevima."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("đ", "dj").replace("Đ", "dj")
    text = text.lower()
    text = re.sub(r"[^\w\s']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_wake_word(text: str) -> Tuple[str, bool]:
    """Uklanja wake word sa početka. Vraća (ostatak, da_li_je_bio)."""
    normalized = normalize(text)
    for wake in sorted(WAKE_WORDS, key=len, reverse=True):
        if normalized == wake:
            return "", True
        if normalized.startswith(wake + " "):
            return normalized[len(wake):].strip(), True
    return normalized, False


def strip_wake_word_raw(text: str) -> Tuple[str, bool]:
    """Uklanja wake word sa početka, ali čuva originalni tekst (velika/mala slova)."""
    raw = (text or "").strip()
    norm = normalize(raw)
    for wake in sorted(WAKE_WORDS, key=len, reverse=True):
        if norm == wake:
            return "", True
        if norm.startswith(wake + " "):
            # Pronađi kraj wake word-a u raw tekstu
            parts = wake.split()
            pattern = r"^\s*" + r"\s+".join(re.escape(p) for p in parts) + r"\s*"
            m = re.match(pattern, raw, re.IGNORECASE)
            if m:
                return raw[m.end():].strip(), True
            return raw[len(wake):].strip(), True
    return raw, False


def is_wake_word_only(text: str) -> bool:
    remainder, had = strip_wake_word(text)
    return had and not remainder


def has_wake_word(text: str) -> bool:
    """Da li tekst sadrži wake word."""
    _, had = strip_wake_word(text)
    return had


def split_wake_word(text: str) -> Tuple[bool, str]:
    """Vrati (ima_wake_word, ostatak_teksta bez wake word-a)."""
    return strip_wake_word(text)


def _extract_number(tokens: Iterable[str], raw: str) -> Optional[int]:
    for token in tokens:
        if token.isdigit():
            try:
                value = int(token)
            except ValueError:
                continue
            if 1 <= value <= 200:
                return value
    for token in tokens:
        if token in _NUMBER_WORDS:
            val = _NUMBER_WORDS[token]
            if 1 <= val <= 200:
                return val
    return None


def _match_phrase(tokens: list) -> Optional[str]:
    if not tokens:
        return None
    for size in (3, 2, 1):
        if len(tokens) >= size:
            phrase = " ".join(tokens[:size])
            if phrase in STOP_WORDS:
                return "stop"
            if phrase in SKIP_WORDS:
                return "skip"
            if phrase in PAUSE_WORDS:
                return "pause"
            if phrase in RESUME_WORDS:
                return "resume"
            if phrase in VOLUME_WORDS:
                return "volume"
            if phrase in PLAY_WORDS:
                return "play"
            if phrase in DISCONNECT_WORDS:
                return "disconnect"
    return None


def _autoplay_mode(tokens: list) -> Optional[str]:
    """Vraća 'on'/'off' ako postoji eksplicitna namera, inače None."""
    for token in tokens:
        if token in AUTOPLAY_ON_WORDS:
            return "on"
    for token in tokens:
        if token in AUTOPLAY_OFF_WORDS:
            return "off"
    return None


def _extract_raw_target(raw_remainder: str, verb_tokens_count: int) -> str:
    """Izvlači originalni naziv korisnika (očuvan casing) nakon glagola."""
    raw_tokens = raw_remainder.split()
    if len(raw_tokens) > verb_tokens_count:
        target = " ".join(raw_tokens[verb_tokens_count:]).strip()
        # Očisti interpunkciju sa krajeva ako postoji
        return target.strip(".,!?\"'")
    return ""


def parse_command(text: str) -> Optional[Tuple[str, str]]:
    """
    Vraća (command, query) ili None ako tekst nije komanda.

    Primeri:
        "Hey Jarvis pusti senidah bez tebe" -> ("play", "senidah bez tebe")
        "Hey Jarvis skip"                   -> ("skip", "")
        "Hey Jarvis jump 3"                 -> ("jump", "3")
        "Hey Jarvis disconnect"             -> ("disconnect", "")
        "Hey Jarvis mute Marko"             -> ("mute", "Marko")
        "Hey Jarvis deafen Stefan"          -> ("deafen", "Stefan")
    """
    remainder, had_wake = strip_wake_word(text)
    raw_remainder, _ = strip_wake_word_raw(text)
    if not remainder:
        return None

    tokens = remainder.split()

    # 1. Disconnect provera (pre ostalih jednorečnih komandi)
    for size in (2, 1):
        if len(tokens) >= size:
            phrase = " ".join(tokens[:size])
            if phrase in DISCONNECT_WORDS:
                return ("disconnect", "")

    # 2. Autoplay on/off provera
    if any(w in remainder for w in AUTOPLAY_WORDS):
        mode = _autoplay_mode(tokens)
        if mode:
            return ("autoplay", mode)

    # 3. Mute / Deafen sa očuvanjem ciljanog korisnika
    for size in (2, 1):
        if len(tokens) >= size:
            phrase = " ".join(tokens[:size])
            if phrase in MUTE_VERBS:
                target = _extract_raw_target(raw_remainder, size)
                if target:
                    return ("mute", target)
                return None
            if phrase in DEAFEN_VERBS:
                target = _extract_raw_target(raw_remainder, size)
                if target:
                    return ("deafen", target)
                return None

    # 4. Jump (1-based index)
    for size in (3, 2, 1):
        if len(tokens) >= size:
            phrase = " ".join(tokens[:size])
            if phrase in JUMP_PREFIXES:
                rem_tokens = tokens[size:]
                val = _extract_number(rem_tokens, remainder)
                if val is not None and val >= 1:
                    return ("jump", str(val))

    command = _match_phrase(tokens)

    # 5. Volume
    if command == "volume":
        value = _extract_number(tokens, remainder)
        if value is not None:
            return ("volume", str(value))
        if any(t.isdigit() or t in _NUMBER_WORDS for t in tokens):
            return None
        if any(w in remainder for w in ("smanji", "utisaj", "down", "dole", "quieter")):
            return ("volume", "-15")
        return ("volume", "+15")

    # 6. Stop, Skip, Pause, Resume
    if command in ("stop", "skip", "pause", "resume", "disconnect"):
        return (command, "")

    # 7. Play
    if command == "play":
        query_tokens = [
            t for t in tokens[1:] if t not in _FILLER_WORDS
        ] if len(tokens) > 1 else []
        query = " ".join(query_tokens).strip()
        if query:
            return ("play", query)
        return None

    # 8. Implicitno puštanje pesme (nema eksplicitnog glagola)
    if had_wake:
        content = [t for t in tokens if t not in _FILLER_WORDS]
        if len(content) >= 2:
            return ("play", " ".join(content))

    return None

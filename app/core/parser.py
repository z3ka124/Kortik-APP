# c:\Kortik\Kortik-Listener-App\app\core\parser.py
"""
Parser glasovnih komandi (bez ijedne spoljne zavisnosti).

Ulaz:  transkribovani tekst (npr. "Kortik pusti senidah bez tebe")
Izlaz: (command, query) gde je command jedan od:
       play | skip | stop | pause | resume | volume | None (nije komanda)

Pravila su namerno ista kao u legacy `Kortik-VoiceListener/stt_parser.py`,
ali bez Vosk zavisnosti — ovako parser radi i u cloud i u lokalnom STT rezimu.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Optional, Tuple

WAKE_WORDS: Tuple[str, ...] = (
    "hej kortik", "hey kortik", "hej kortik", "ej kortik",
    "kortik", "kortiku", "kortik.",
    "hej jarvis", "hey jarvis", "jarvis",
)

STOP_WORDS = {
    "stop", "stani", "stanite", "ugasi", "prekini", "zaustavi", "cuti", "prestani", "dosta",
}
SKIP_WORDS = {
    "skip", "preskoci", "dalje", "sledeca", "sledecu", "next", "druga", "prebaci", "promeni",
}
PAUSE_WORDS = {"pause", "pauza", "pauziraj", "cekaj", "wait", "pauzu"}
RESUME_WORDS = {"resume", "nastavi", "unpause", "kreni", "continue", "pusti dalje"}
VOLUME_WORDS = {
    "volume", "volumen", "glasnoca", "glasnocu", "jacina", "pojacaj", "smanji", "utisaj",
    "volume up", "volume down",
}
PLAY_WORDS = {
    "play", "pusti", "pustaj", "sviraj", "dodaj", "opali", "daj", "ukljuci", "reprodukuj",
    "pokreni", "zapocni",
}

_NUMBER_WORDS = {
    "nula": 0, "zero": 0,
    "jedan": 1, "one": 1, "jednu": 1,
    "dva": 2, "two": 2, "dve": 2,
    "tri": 3, "three": 3,
    "cetiri": 4, "four": 4,
    "pet": 5, "five": 5,
    "sest": 6, "six": 6,
    "sedam": 7, "seven": 7,
    "osam": 8, "eight": 8,
    "devet": 9, "nine": 9,
    "deset": 10, "ten": 10,
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
    "bre", "brate", "kortik", "mi", "nam", "vam", "moze", "mozes",
}


def normalize(text: str) -> str:
    """Mala slova, bez dijakritika, bez viska razmaka i interpunkcije na krajevima."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", str(text))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.replace("đ", "dj").replace("Đ", "dj")
    text = text.lower()
    text = re.sub(r"[^\w\s']", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_wake_word(text: str) -> Tuple[str, bool]:
    """Uklanja wake word sa pocetka. Vraca (ostatak, da_li_je_bio)."""
    normalized = normalize(text)
    for wake in sorted(WAKE_WORDS, key=len, reverse=True):
        if normalized == wake:
            return "", True
        if normalized.startswith(wake + " "):
            return normalized[len(wake):].strip(), True
    return normalized, False


def is_wake_word_only(text: str) -> bool:
    remainder, had = strip_wake_word(text)
    return had and not remainder


def _extract_number(tokens: Iterable[str], raw: str) -> Optional[int]:
    for token in tokens:
        if token.isdigit():
            try:
                value = int(token)
            except ValueError:
                continue
            if 0 <= value <= 200:
                return value
    for token in tokens:
        if token in _NUMBER_WORDS:
            return _NUMBER_WORDS[token]
    return None


def _match_phrase(tokens: list) -> Optional[str]:
    if not tokens:
        return None
    for size in (2, 1):
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
    return None


def parse_command(text: str) -> Optional[Tuple[str, str]]:
    """
    Vraca (command, query) ili None ako tekst nije komanda.

    Primeri:
        "Kortik pusti senidah bez tebe" -> ("play", "senidah bez tebe")
        "Kortik skip"                   -> ("skip", "")
        "Kortik glasnoca 80"            -> ("volume", "80")
        "Kortik pojacaj"                -> ("volume", "+15")
        "kako si"                       -> None
    """
    remainder, had_wake = strip_wake_word(text)
    if not remainder:
        return None

    tokens = remainder.split()
    command = _match_phrase(tokens)

    if command == "volume":
        value = _extract_number(tokens, remainder)
        if value is not None:
            return ("volume", str(value))
        if any(w in remainder for w in ("smanji", "utisaj", "down", "dole")):
            return ("volume", "-15")
        return ("volume", "+15")

    if command in ("stop", "skip", "pause", "resume"):
        return (command, "")

    if command == "play":
        query_tokens = [
            t for t in tokens[1:] if t not in _FILLER_WORDS
        ] if len(tokens) > 1 else []
        query = " ".join(query_tokens).strip()
        if query:
            return ("play", query)
        return None

    # Nema eksplicitnog glagola: ako je recenica posle wake word-a dovoljno
    # "sadrzajna", tretiramo je kao zahtev za pesmu ("Kortik senidah bez tebe").
    if had_wake:
        content = [t for t in tokens if t not in _FILLER_WORDS]
        if len(content) >= 2:
            return ("play", " ".join(content))

    return None

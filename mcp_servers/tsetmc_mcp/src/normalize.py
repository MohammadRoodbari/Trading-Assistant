"""Persian / Arabic text and digit normalization.

TSETMC stores symbols with Persian letters (ی U+06CC, ک U+06A9) but user input
frequently arrives with the Arabic forms (ي U+064A, ك U+0643). Numbers may also
come in Persian or Arabic-Indic digits. Everything is normalized to a single
canonical form before matching or numeric parsing, otherwise lookups silently miss.
"""

from __future__ import annotations

import unicodedata

# Arabic -> Persian letter folding (the two that actually differ in symbols).
_LETTER_MAP = {
    "ي": "ی",  # ARABIC YEH -> FARSI YEH
    "ى": "ی",  # ALEF MAKSURA -> FARSI YEH
    "ك": "ک",  # ARABIC KAF -> KEHEH
    "ة": "ه",  # TEH MARBUTA -> HEH (rare in names)
}

# Persian (U+06F0..) and Arabic-Indic (U+0660..) digits -> ASCII.
_DIGIT_MAP = {}
for i in range(10):
    _DIGIT_MAP[chr(0x06F0 + i)] = str(i)  # Persian
    _DIGIT_MAP[chr(0x0660 + i)] = str(i)  # Arabic-Indic
_DIGIT_MAP["٫"] = "."  # Arabic decimal separator
_DIGIT_MAP["٬"] = ","  # Arabic thousands separator

_TRANS = {ord(k): v for k, v in {**_LETTER_MAP, **_DIGIT_MAP}.items()}


def fold_digits(text: str) -> str:
    """Convert Persian/Arabic digits (and separators) to ASCII."""
    return text.translate({ord(k): v for k, v in _DIGIT_MAP.items()})


def normalize_text(text: str | None) -> str:
    """Canonicalize a Persian string: fold Arabic letters + digits, strip ALL
    Unicode format/bidi marks (category Cf: ZWNJ/ZWJ, LRM/RLM, BOM, isolates…),
    collapse whitespace. Safe on None and on non-str input (coerced to str)."""
    if text is None:
        return ""
    if not isinstance(text, str):
        text = str(text)
    if not text:
        return ""
    out = text.translate(_TRANS)
    # Drop every Unicode "format" char (Cf) — covers the full zero-width/bidi set,
    # which is one-sided noise (only user input carries it, never the clean index).
    out = "".join(ch for ch in out if unicodedata.category(ch) != "Cf")
    return " ".join(out.split()).strip()


def normalize_symbol(symbol: str | None) -> str:
    """Normalization key for matching a نماد. Same as normalize_text but also
    drops internal spaces so 'شست' and ' ش س ت ' compare equal-ish for lookup."""
    return normalize_text(symbol).replace(" ", "")


def to_number(value, default=None):
    """Best-effort numeric parse tolerant of Persian digits, commas, blanks,
    and TSETMC's habit of returning '' or None for missing values."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value
    s = fold_digits(str(value)).replace(",", "").strip()
    if s == "" or s.lower() in {"none", "null", "nan"}:
        return default
    try:
        f = float(s)
    except ValueError:
        return default
    return int(f) if f.is_integer() else f

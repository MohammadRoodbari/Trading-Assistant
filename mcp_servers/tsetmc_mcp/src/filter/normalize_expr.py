"""Translate a pasted TSETMC filter (or friendly alias syntax) into the canonical
expression our safe evaluator understands.

Handles TSETMC conventions: `(pl)` parenthesized tokens, `(ct).Buy_I_Volume`
client-type access, `&&`/`||`/`!` operators, and the `buy_queue()`/`sell_queue()`
sugar macros. Rewrites are applied only OUTSIDE string literals so a quoted value
like `contains(name, "a&&b")` is left intact. Friendly Python-ish expressions pass
through unchanged. History/aggregate bracket terms ([ih], [is..]) are rejected.
"""

from __future__ import annotations

import re

from .safe_eval import FilterError

# صف sugar → order-book expression. A buy queue = ask side empty + real bid waiting.
_SUGAR = {
    "buy_queue": "((qo1 == 0 or po1 == 0) and qd1 > 0)",
    "sell_queue": "((qd1 == 0 or pd1 == 0) and qo1 > 0)",
}

_CT_MAP = {
    "Buy_I_Volume": "ct_buy_i_vol",
    "Sell_I_Volume": "ct_sell_i_vol",
    "Buy_CountI": "ct_buy_count_i",
    "Sell_CountI": "ct_sell_count_i",
    "Buy_N_Volume": "ct_buy_n_vol",
    "Sell_N_Volume": "ct_sell_n_vol",
    "Buy_CountN": "ct_buy_count_n",
    "Sell_CountN": "ct_sell_count_n",
}
_CT_MAP_CI = {k.lower(): v for k, v in _CT_MAP.items()}

# Strip TSETMC parens around a single token: (pl) -> pl. A leading identifier means
# it's a function call (abs(x), even `abs (x)`) and is preserved. `and/or/not` before
# parens are keywords, not calls, so they don't count as the leading identifier.
_TOKEN_PAREN = re.compile(
    r"(?<![\w)])((?!and\b|or\b|not\b)[A-Za-z_]\w*\s*)?\(\s*([A-Za-z_]\w*)\s*\)"
)
_CT_ACCESS = re.compile(r"\(\s*ct\s*\)\s*\.\s*(\w+)", re.IGNORECASE)
_SUGAR_CALL = re.compile(r"\b(buy_queue|sell_queue)\s*\(\s*\)")
# `!x` -> `(not x)` — wraps its immediate operand so C-style tight precedence is kept
# (Python `not` binds looser). Leaves `!=` alone.
_NOT = re.compile(r"!(?!=)\s*(\([^()]*\)|[\w.]+)")
_HISTORY = re.compile(r"\[\s*(ih|is\d*)\s*\]", re.IGNORECASE)
_STRING_SPLIT = re.compile(r"(\"[^\"]*\"|'[^']*')")


def _ct(m: re.Match) -> str:
    norm = _CT_MAP_CI.get(m.group(1).lower())
    if norm is None:
        raise FilterError(f"unknown client-type field: (ct).{m.group(1)}")
    return norm


def _paren_repl(m: re.Match) -> str:
    return m.group(0) if m.group(1) else m.group(2)


def _rewrite(s: str) -> str:
    """Apply all rewrites to a non-string fragment."""
    s = _SUGAR_CALL.sub(lambda m: _SUGAR[m.group(1)], s)
    s = _CT_ACCESS.sub(_ct, s)
    s = s.replace("&&", " and ").replace("||", " or ")
    s = _NOT.sub(r"(not \1)", s)
    s = _TOKEN_PAREN.sub(_paren_repl, s)
    return " ".join(s.split())


def normalize(raw: str) -> str:
    if not raw or not raw.strip():
        raise FilterError("empty filter expression")
    s = raw.strip()
    if _HISTORY.search(s) or ".QTotTran5J" in s or ".PClosing" in s:
        raise FilterError(
            "history/aggregate terms ([ih], [is..], 30-day averages) aren't supported "
            "in v1. Remove them, or use a snapshot proxy like `volume > 3 * base_volume`."
        )
    # Rewrite only the non-string spans; keep string literals verbatim.
    parts = _STRING_SPLIT.split(s)
    for i in range(0, len(parts), 2):
        parts[i] = _rewrite(parts[i])
    return "".join(parts).strip()

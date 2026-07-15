"""Output shaping — the context-window guard.

The market snapshot holds ~700 instruments with ~18 fields each. Dumping that at
the model would blow its context, so every market-wide tool MUST filter, sort,
project to a compact field set, and hard-limit. These helpers centralize that so
no tool can accidentally return the raw snapshot.
"""

from __future__ import annotations

from collections.abc import Callable

from .config import Config
from .models import Instrument
from .normalize import normalize_symbol

# Compact projection used unless the caller asks for specific fields.
COMPACT_FIELDS = ("symbol", "name", "last", "close", "pct_change", "volume", "value")

_SORT_KEYS: dict[str, Callable[[Instrument], float]] = {
    "pct_change": lambda i: i.pct_change if i.pct_change is not None else float("-inf"),
    "volume": lambda i: i.volume or 0,
    "value": lambda i: i.value or 0,
    "last": lambda i: i.last or 0,
    "count": lambda i: i.count or 0,
}


def project(inst: Instrument, fields: list[str] | None) -> dict:
    full = inst.to_dict()
    keys = fields or COMPACT_FIELDS
    # Always keep an identifier so results are actionable.
    out = {"ins_code": inst.ins_code}
    for k in keys:
        if k in full:
            out[k] = full[k]
    return out


def clamp_limit(cfg: Config, limit: int | None) -> int:
    if not limit or limit <= 0:
        return cfg.default_limit
    return min(limit, cfg.max_limit)


def filter_and_sort(
    rows: list[Instrument],
    *,
    min_pct: float | None = None,
    max_pct: float | None = None,
    min_volume: int | None = None,
    min_value: int | None = None,
    flow: int | None = None,
    symbol_contains: str | None = None,
    traded_only: bool = False,
    sort_by: str = "value",
    descending: bool = True,
) -> list[Instrument]:
    contains = normalize_symbol(symbol_contains) if symbol_contains else None
    out = []
    for i in rows:
        pc = i.pct_change
        # traded_only drops symbols with no trade today (pct_change is None) so
        # gainer/loser screens never surface untraded names.
        if traded_only and pc is None:
            continue
        if min_pct is not None and (pc is None or pc < min_pct):
            continue
        if max_pct is not None and (pc is None or pc > max_pct):
            continue
        if min_volume is not None and (i.volume or 0) < min_volume:
            continue
        if min_value is not None and (i.value or 0) < min_value:
            continue
        if flow is not None and i.flow != flow:
            continue
        if contains and contains not in normalize_symbol(i.symbol):
            continue
        out.append(i)
    key = _SORT_KEYS.get(sort_by, _SORT_KEYS["value"])
    out.sort(key=key, reverse=descending)
    return out


def shape(
    cfg: Config,
    rows: list[Instrument],
    *,
    limit: int | None = None,
    fields: list[str] | None = None,
    **filters,
) -> dict:
    """Filter+sort+limit+project, returning {rows, returned, matched, truncated}."""
    filtered = filter_and_sort(rows, **filters)
    lim = clamp_limit(cfg, limit)
    page = filtered[:lim]
    return {
        "rows": [project(i, fields) for i in page],
        "returned": len(page),
        "matched": len(filtered),
        "truncated": len(filtered) > lim,
    }

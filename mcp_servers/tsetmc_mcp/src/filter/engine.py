"""The filter engine: compile a filter, scan the snapshot, enrich for order-book.

Flow:
  1. normalize the (possibly TSETMC-syntax) expression, compile+validate it safely;
  2. reject known-unsupported variables with a clear message;
  3. if the filter uses ONLY snapshot/client-type names -> evaluate over every
     instrument instantly and return the matches;
  4. if it uses order-book names (صف / depth) -> run the snapshot-only part of the
     filter first to get candidates, cap them to `enrich_limit` most-liquid names,
     fetch each order book on demand, then apply the FULL filter. This keeps an
     order-book filter to a bounded number of fetches — never a 700-symbol scan.
"""

from __future__ import annotations

import ast

from ..fetch import TsetmcError
from .normalize_expr import normalize
from .safe_eval import Filter, FilterError, compile_filter, make_safe_funcs
from .variables import (
    ALLOWED_NAMES,
    ORDERBOOK_NAMES,
    SNAPSHOT_NAMES,
    UNSUPPORTED,
    augment_orderbook,
    build_row,
)

_FUNCS = make_safe_funcs()
_FUNC_NAMES = frozenset(_FUNCS)
_COMPILE_NAMES = ALLOWED_NAMES | set(UNSUPPORTED)

# Fields always shown for a match, plus any the filter referenced.
_DISPLAY_BASE = ("last", "change_pct", "volume", "value")


def _compile(raw: str) -> tuple[Filter, str, bool]:
    """normalize + compile + classify. Returns (filter, normalized, is_enriched)."""
    canonical = normalize(raw)
    filt = compile_filter(canonical, _COMPILE_NAMES, _FUNCS)
    bad = filt.names & set(UNSUPPORTED)
    if bad:
        name = sorted(bad)[0]
        raise FilterError(UNSUPPORTED[name])
    enriched = bool(filt.names & ORDERBOOK_NAMES)
    return filt, canonical, enriched


def _flatten_and(node):
    """Yield AND-conjuncts, descending recursively through nested `and` only."""
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.And):
        for v in node.values:
            yield from _flatten_and(v)
    else:
        yield node


def _snapshot_prefilter(canonical: str) -> Filter | None:
    """Build a filter from the AND-conjuncts (at any nesting depth) that use only
    snapshot names, to pre-narrow candidates before order-book enrichment."""
    body = ast.parse(canonical, mode="eval").body
    keep = []
    for c in _flatten_and(body):
        names = {n.id for n in ast.walk(c) if isinstance(n, ast.Name)} - _FUNC_NAMES
        if names and names <= SNAPSHOT_NAMES:
            keep.append(ast.unparse(c))
    if not keep:
        return None
    return compile_filter(" and ".join(f"({s})" for s in keep), ALLOWED_NAMES, _FUNCS)


def validate(raw: str) -> str:
    """Normalize + compile a filter WITHOUT running it. Returns the normalized
    expression; raises FilterError if invalid. Used to validate before saving."""
    _, canonical, _ = _compile(raw)
    return canonical


def _display(inst, row: dict, used: frozenset) -> dict:
    out = {"ins_code": inst.ins_code, "symbol": inst.symbol, "name": inst.name}
    for k in _DISPLAY_BASE:
        out[k] = _clean(row.get(k))
    for k in sorted(used):  # show the fields the filter actually used
        if k not in out and k in row:
            out[k] = _clean(row[k])
    return out


def _clean(v):
    # NaN -> None for JSON; keep ints tidy.
    if isinstance(v, float):
        if v != v:
            return None
        return int(v) if v.is_integer() else round(v, 4)
    return v


async def run(
    raw: str, snapshot, source, *, limit: int = 20, enrich_limit: int = 30, sort_by: str = "value"
) -> dict:
    filt, canonical, enriched = _compile(raw)

    instruments = list(snapshot.instruments.values())
    base = [(i, build_row(i, snapshot.client_type.get(i.ins_code))) for i in instruments]

    uses_ct = any(
        n.startswith("ct_") or n in ("net_individual", "buyer_power", "percap_buy", "percap_sell")
        for n in filt.names
    )
    result = {
        "expression": raw,
        "normalized": canonical,
        "tier": "enriched" if enriched else "snapshot",
        "universe": len(instruments),
        # Distinguishes "no stock qualified" from "money-flow data missing this poll".
        "client_type_symbols": len(snapshot.client_type),
        "uses_money_flow": uses_ct,
    }
    if uses_ct and not snapshot.client_type:
        result["money_flow_warning"] = (
            "this filter uses حقیقی/حقوقی data but the "
            "client-type snapshot is empty (poll failed or market closed) "
            "— a 0 match may just mean missing data"
        )

    if not enriched:
        matched = [(i, r) for i, r in base if filt.evaluate(r)]
        matched.sort(key=lambda ir: _sort_key(ir[1], sort_by), reverse=True)
        result.update(
            {
                "matched": len(matched),
                "returned": min(len(matched), limit),
                "truncated": len(matched) > limit,
                "rows": [_display(i, r, filt.names) for i, r in matched[:limit]],
            }
        )
        return result

    # enriched (order-book) path: prefilter -> cap -> fetch order books -> full filter
    prefilter = _snapshot_prefilter(canonical)
    candidates = [(i, r) for i, r in base if (prefilter is None or prefilter.evaluate(r))]
    candidates.sort(key=lambda ir: _sort_key(ir[1], "value"), reverse=True)
    capped = candidates[:enrich_limit]

    matched = []
    fetched = 0
    for inst, row in capped:
        try:
            levels = await source.order_book(inst.ins_code)
            fetched += 1
        except TsetmcError:
            continue
        augment_orderbook(row, levels)
        if filt.evaluate(row):
            matched.append((inst, row))
    matched.sort(key=lambda ir: _sort_key(ir[1], sort_by), reverse=True)
    result.update(
        {
            "matched": len(matched),
            "returned": min(len(matched), limit),
            "candidates_prefiltered": len(candidates),
            "order_books_fetched": fetched,
            "enrich_capped": len(candidates) > enrich_limit,
            "has_snapshot_prefilter": prefilter is not None,
            "rows": [_display(i, r, filt.names) for i, r in matched[:limit]],
            "note": (
                None
                if prefilter is not None
                else "filter had no snapshot condition, so only the top instruments by "
                "value were order-book-enriched; add a snapshot condition (e.g. value>0) to target better"
            ),
        }
    )
    return result


def _sort_key(row: dict, field: str) -> float:
    v = row.get(field, row.get("value"))
    if isinstance(v, float) and v != v:
        return float("-inf")
    return v if isinstance(v, (int, float)) else float("-inf")

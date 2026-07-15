"""Tool business logic, independent of MCP.

Every MCP tool in server.py is a thin wrapper over one method here. Keeping the
logic MCP-free means it can be unit-tested against a fixture snapshot with no
network and no server. All market-wide reads come from the Snapshot; only
per-symbol lookups (order book, history, cache-miss quotes/search) touch the
network, serialized through the source's rate limiter.
"""

from __future__ import annotations

import csv

from .config import Config
from .fetch import MarketDataSource, TsetmcError
from .filter import FilterError, run_filter
from .filter import store as filter_store
from .filter.engine import validate as validate_filter
from .filter.presets import PRESETS
from .filter.variables import VARIABLE_DOCS
from .shaping import clamp_limit, shape
from .snapshot import Snapshot

# Inline rows above this force a CSV file instead of dumping into the response.
_INLINE_HISTORY_CAP = 60


class Service:
    def __init__(self, cfg: Config, source: MarketDataSource, snapshot: Snapshot):
        self._cfg = cfg
        self._source = source
        self._snap = snapshot

    # ------------------------------------------------------------------ helpers
    async def _resolve(self, symbol_or_code: str) -> tuple[str | None, dict | None]:
        """Return (ins_code, match_info). Tries the snapshot first, then a live
        search. match_info carries the resolved symbol/name when known."""
        ins = self._snap.resolve(symbol_or_code)
        if ins:
            inst = self._snap.get(ins)
            info = {"symbol": inst.symbol, "name": inst.name} if inst else None
            return ins, info
        # Cache miss -> live search.
        try:
            hits = await self._source.search(symbol_or_code)
        except TsetmcError:
            return None, None
        if hits:
            h = hits[0]
            return h["ins_code"] or None, {"symbol": h["symbol"], "name": h["name"]}
        return None, None

    def _not_found(self, symbol: str) -> dict:
        return {
            "error": "symbol_not_found",
            "query": symbol,
            "hint": "Pass a Persian نماد (e.g. 'فولاد') or a numeric insCode. "
            "Market may be closed / snapshot warming; try search_symbol first.",
            "meta": self._snap.meta(),
        }

    # ------------------------------------------------------------------ tools
    async def search_symbol(self, query: str, limit: int = 10) -> dict:
        # Prefer the in-memory index (instant, no network) then fill from live search.
        limit = clamp_limit(self._cfg, limit)
        results: list[dict] = []
        seen: set[str] = set()
        from .normalize import normalize_symbol

        key = normalize_symbol(query)
        for norm, ins in self._snap.symbol_index.items():
            if key and key in norm:
                inst = self._snap.get(ins)
                if inst and ins not in seen:
                    seen.add(ins)
                    results.append({"ins_code": ins, "symbol": inst.symbol, "name": inst.name})
        if len(results) < limit:
            try:
                for h in await self._source.search(query):
                    if h["ins_code"] and h["ins_code"] not in seen:
                        seen.add(h["ins_code"])
                        results.append(h)
            except TsetmcError as exc:
                if not results:
                    return {"error": "unreachable", "detail": str(exc), "meta": self._snap.meta()}
        return {"query": query, "results": results[:limit], "meta": self._snap.meta()}

    async def get_quote(self, symbol: str) -> dict:
        ins, info = await self._resolve(symbol)
        if not ins:
            return self._not_found(symbol)
        inst = self._snap.get(ins)
        served = "snapshot"
        # Fall back to a live per-symbol fetch when the snapshot has no usable price:
        # symbol absent, or market closed so GetMarketWatch zeroed the intraday fields
        # (the per-symbol endpoint keeps the last valid session values).
        if inst is None or (inst.last is None and inst.close is None):
            live = None
            try:
                live = await self._source.quote(ins)
            except TsetmcError as exc:
                if inst is None:
                    return {"error": "unreachable", "detail": str(exc), "meta": self._snap.meta()}
            if live is not None and (live.last is not None or live.close is not None):
                inst, served = live, "live"
            elif inst is None:
                inst, served = live, "live"
        if inst is None:
            return self._not_found(symbol)
        out = inst.to_dict()
        if info:  # backfill symbol/name if the live single-quote lacked them
            out["symbol"] = out.get("symbol") or info.get("symbol", "")
            out["name"] = out.get("name") or info.get("name", "")
        return {"quote": out, "meta": self._snap.meta(served)}

    async def get_order_book(self, symbol: str) -> dict:
        ins, info = await self._resolve(symbol)
        if not ins:
            return self._not_found(symbol)
        try:
            levels = await self._source.order_book(ins)  # always live per-symbol
        except TsetmcError as exc:
            return {"error": "unreachable", "detail": str(exc), "meta": self._snap.meta()}
        return {
            "ins_code": ins,
            "symbol": (info or {}).get("symbol", ""),
            "order_book": [lv.to_dict() for lv in levels],
            "meta": self._snap.meta("live"),
        }

    async def get_money_flow(self, symbol: str) -> dict:
        ins, info = await self._resolve(symbol)
        if not ins:
            return self._not_found(symbol)
        ct = self._snap.client_type.get(ins)
        served = "snapshot"
        if ct is None:
            try:
                ct = await self._source.client_type(ins)
                served = "live"
            except TsetmcError as exc:
                return {"error": "unreachable", "detail": str(exc), "meta": self._snap.meta()}
        if ct is None:
            return {"error": "no_money_flow", "ins_code": ins, "meta": self._snap.meta()}
        return {
            "ins_code": ins,
            "symbol": (info or {}).get("symbol", ""),
            "money_flow": ct.to_dict(),
            "meta": self._snap.meta(served),
        }

    def get_market_watch(
        self,
        limit: int | None = None,
        sort_by: str = "value",
        descending: bool = True,
        min_pct: float | None = None,
        max_pct: float | None = None,
        min_volume: int | None = None,
        min_value: int | None = None,
        flow: int | None = None,
        symbol_contains: str | None = None,
        fields: list[str] | None = None,
    ) -> dict:
        rows = list(self._snap.instruments.values())
        result = shape(
            self._cfg,
            rows,
            limit=limit,
            fields=fields,
            sort_by=sort_by,
            descending=descending,
            min_pct=min_pct,
            max_pct=max_pct,
            min_volume=min_volume,
            min_value=min_value,
            flow=flow,
            symbol_contains=symbol_contains,
        )
        result["meta"] = self._snap.meta()
        return result

    def screen(self, kind: str = "top_gainers", limit: int | None = None) -> dict:
        rows = list(self._snap.instruments.values())
        presets = {
            "top_gainers": dict(sort_by="pct_change", descending=True, traded_only=True),
            "top_losers": dict(sort_by="pct_change", descending=False, traded_only=True),
            "most_active_value": dict(sort_by="value", descending=True),
            "most_active_volume": dict(sort_by="volume", descending=True),
            "most_active_trades": dict(sort_by="count", descending=True),
        }
        if kind == "market_breadth":
            adv = dec = unch = 0
            for i in rows:
                pc = i.pct_change
                if pc is None:  # untraded / no reference -> classified separately
                    continue
                if pc > 0:
                    adv += 1
                elif pc < 0:
                    dec += 1
                else:
                    unch += 1
            classified = adv + dec + unch
            return {
                "kind": kind,
                "breadth": {
                    "advancers": adv,
                    "decliners": dec,
                    "unchanged": unch,
                    "classified": classified,
                    "untraded": len(rows) - classified,
                    "total": len(rows),
                },
                "meta": self._snap.meta(),
            }
        if kind not in presets:
            return {
                "error": "unknown_screen",
                "kind": kind,
                "available": list(presets) + ["market_breadth"],
                "meta": self._snap.meta(),
            }
        result = shape(self._cfg, rows, limit=limit, **presets[kind])
        result["kind"] = kind
        result["meta"] = self._snap.meta()
        return result

    async def get_index_overview(self) -> dict:
        ov = self._snap.overview
        served = "snapshot"
        if ov is None:
            try:
                ov = await self._source.market_overview()
                served = "live"
            except TsetmcError as exc:
                return {"error": "unreachable", "detail": str(exc), "meta": self._snap.meta()}
        return {"overview": ov.to_dict() if ov else None, "meta": self._snap.meta(served)}

    async def get_price_history(self, symbol: str, days: int = 30, save_csv: bool = False) -> dict:
        ins, info = await self._resolve(symbol)
        if not ins:
            return self._not_found(symbol)
        try:
            rows = await self._source.price_history(ins, days)
        except TsetmcError as exc:
            return {"error": "unreachable", "detail": str(exc), "meta": self._snap.meta()}
        if not rows:
            return {"error": "no_history", "ins_code": ins, "meta": self._snap.meta()}

        closes = [r["close"] for r in rows if r["close"] is not None]
        summary = {
            "rows": len(rows),
            "from": rows[0]["date_jalali"],
            "to": rows[-1]["date_jalali"],
            "min_close": min(closes) if closes else None,
            "max_close": max(closes) if closes else None,
            "last_close": rows[-1]["close"],
        }
        # Large pulls (or explicit request) go to a CSV file; return path + summary.
        if save_csv or len(rows) > _INLINE_HISTORY_CAP:
            path = self._write_history_csv(ins, (info or {}).get("symbol", ""), rows)
            return {
                "ins_code": ins,
                "symbol": (info or {}).get("symbol", ""),
                "file_path": str(path),
                "summary": summary,
                "sample": rows[-5:],
                "meta": self._snap.meta("live"),
                "note": "Full series written to CSV (kept out of the context window). "
                "Read the file if you need every row.",
            }
        return {
            "ins_code": ins,
            "symbol": (info or {}).get("symbol", ""),
            "history": rows,
            "summary": summary,
            "meta": self._snap.meta("live"),
        }

    def _write_history_csv(self, ins: str, symbol: str, rows: list[dict]):
        self._cfg.ensure_dirs()
        safe = symbol.replace("/", "_") or ins
        # Deterministic name (no timestamp) so re-pulls overwrite rather than pile up.
        path = self._cfg.history_dir / f"{ins}_{safe}.csv"
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return path

    # ------------------------------------------------------------------ filters
    def _invalid(self, expression: str, exc: Exception) -> dict:
        return {
            "error": "invalid_filter",
            "detail": str(exc),
            "expression": expression,
            "hint": "See filter_help() for valid variables/operators.",
            "meta": self._snap.meta(),
        }

    async def run_filter(
        self,
        expression: str,
        limit: int = 20,
        enrich_limit: int = 30,
        save_as: str | None = None,
        description: str = "",
    ) -> dict:
        # Saving works even off-session; validate first and refuse preset collisions.
        if save_as:
            if save_as in PRESETS:
                return {
                    "error": "name_conflicts_with_preset",
                    "name": save_as,
                    "hint": "that name is a built-in preset; choose a different save_as",
                    "meta": self._snap.meta(),
                }
            try:
                validate_filter(expression)
            except FilterError as exc:
                return self._invalid(expression, exc)
            filter_store.save(self._cfg, save_as, expression, description)

        if not self._snap.is_warm():
            out = {
                "error": "snapshot_cold",
                "hint": "The snapshot is empty (market closed / poller warming). "
                "Filters run over live market data during Tehran session hours.",
                "meta": self._snap.meta(),
            }
            if save_as:
                out["saved_as"] = save_as
            return out

        try:
            res = await run_filter(
                expression,
                self._snap,
                self._source,
                limit=clamp_limit(self._cfg, limit),
                enrich_limit=enrich_limit,
            )
        except FilterError as exc:
            return self._invalid(expression, exc)
        meta = self._snap.meta()
        if save_as:
            res["saved_as"] = save_as
        if not meta["market_open"]:
            res["stale_session_warning"] = (
                "market is closed — results reflect the last snapshot, not live prices"
            )
        res["meta"] = meta
        return res

    async def run_saved_filter(self, name: str, limit: int = 20, enrich_limit: int = 30) -> dict:
        entry = filter_store.get(self._cfg, name) or PRESETS.get(name)
        if not entry:
            saved = list(filter_store.load_all(self._cfg))
            return {
                "error": "unknown_filter",
                "name": name,
                "available_presets": list(PRESETS),
                "available_saved": saved,
                "meta": self._snap.meta(),
            }
        res = await self.run_filter(entry["expression"], limit=limit, enrich_limit=enrich_limit)
        res["filter_name"] = name
        res["description"] = entry.get("description", "")
        return res

    def filter_help(self) -> dict:
        return {
            "how_to": "Write a boolean expression over a symbol's fields; matching symbols "
            "are returned. Accepts TSETMC syntax ((pl)>(py) && (tvol)>0) or friendly aliases "
            "(last>yesterday and volume>0). Pass it to run_filter, optionally save_as a name.",
            "variables": VARIABLE_DOCS,
            "operators": ["and/&&", "or/||", "not/!", "== != < <= > >=", "+ - * / %"],
            "functions": [
                "abs(x)",
                "min(a,b,..)",
                "max(a,b,..)",
                "round(x,n)",
                "startswith(symbol,'x')",
                "endswith(symbol,'x')",
                "contains(name,'x')",
            ],
            "sugar": ["buy_queue()  — locked in صف خرید", "sell_queue()  — locked in صف فروش"],
            "presets": {k: v["description"] for k, v in PRESETS.items()},
            "saved": {
                k: v.get("description", "") for k, v in filter_store.load_all(self._cfg).items()
            },
            "notes": [
                "Order-book filters (buy_queue/sell_queue/pd1..) enrich a shortlist on demand, "
                "capped by enrich_limit — always pair them with a snapshot condition.",
                "History terms ([ih], 30-day averages, RSI) and market_cap/sector are not in v1.",
                "Prices are in Rial; filters run over the live snapshot during market hours.",
            ],
        }

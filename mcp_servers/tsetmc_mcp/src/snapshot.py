"""In-process market snapshot — the single source every tool reads from.

The poller writes here; tools read here. No LLM tool call ever triggers a live
upstream fetch for market-wide data. Every read is stamped with freshness metadata
(dual Jalali/Gregorian date, staleness, market-open, upstream reachability) so the
model can never mistake a frozen or stale snapshot for live data.
"""

from __future__ import annotations

import time
from datetime import datetime

from .calendar_tsec import is_market_open, now_tehran
from .config import Config
from .jalali import stamp
from .models import ClientType, Instrument, MarketOverview
from .normalize import fold_digits, normalize_symbol


class Snapshot:
    def __init__(self, cfg: Config):
        self._cfg = cfg
        self.instruments: dict[str, Instrument] = {}
        self.symbol_index: dict[str, str] = {}  # normalized symbol -> ins_code
        self.client_type: dict[str, ClientType] = {}
        self.overview: MarketOverview | None = None

        self.updated_epoch: float = 0.0
        self.updated_dt: datetime | None = None
        self.upstream_reachable: bool = False
        self.last_error: str | None = None
        self.poll_count: int = 0

    # --- writes (poller) ---
    def update_prices(self, rows: list[Instrument]) -> None:
        if not rows:
            return
        insts: dict[str, Instrument] = {}
        index: dict[str, str] = {}
        for inst in rows:
            if not inst.ins_code:
                continue
            insts[inst.ins_code] = inst
            if inst.symbol:
                index[normalize_symbol(inst.symbol)] = inst.ins_code
        self.instruments = insts
        self.symbol_index = index
        self._mark_updated()

    def update_client_type(self, rows: list[ClientType]) -> None:
        if rows:
            self.client_type = {r.ins_code: r for r in rows if r.ins_code}

    def update_overview(self, ov: MarketOverview) -> None:
        if ov:
            self.overview = ov

    def _mark_updated(self) -> None:
        self.updated_epoch = time.time()
        self.updated_dt = now_tehran(self._cfg)
        self.upstream_reachable = True
        self.poll_count += 1

    def mark_error(self, err: str) -> None:
        self.upstream_reachable = False
        self.last_error = err

    # --- reads (tools) ---
    def is_warm(self) -> bool:
        return bool(self.instruments)

    def resolve(self, symbol_or_code: str) -> str | None:
        """Map a Persian نماد OR a numeric insCode to an insCode present in the
        snapshot. Returns None if unknown here (caller may fall back to search)."""
        s = (symbol_or_code or "").strip()
        if not s:
            return None
        # insCodes may arrive with Persian/Arabic digits — fold before matching so
        # a code like '۴۶۳...' resolves the same as its ASCII form.
        folded = fold_digits(s)
        if folded in self.instruments:  # already an insCode
            return folded
        key = normalize_symbol(s)
        if key in self.symbol_index:
            return self.symbol_index[key]
        # Bare-digit insCode not in snapshot: still return it so on-demand fetch works.
        if folded.isdigit():
            return folded
        return None

    def get(self, ins_code: str) -> Instrument | None:
        return self.instruments.get(ins_code)

    def staleness_seconds(self) -> float | None:
        if not self.updated_epoch:
            return None
        return round(time.time() - self.updated_epoch, 1)

    def meta(self, source_label: str = "snapshot") -> dict:
        """The freshness block attached to every tool response."""
        now = now_tehran(self._cfg)
        as_of = None
        if self.updated_dt is not None:
            as_of = {
                **stamp(self.updated_dt.date()),
                "time": self.updated_dt.strftime("%H:%M:%S"),
            }
        return {
            "source": f"{self._cfg.source}:{source_label}",
            "as_of": as_of,
            "staleness_seconds": self.staleness_seconds(),
            "market_open": is_market_open(self._cfg, now),
            "upstream_reachable": self.upstream_reachable,
            "instrument_count": len(self.instruments),
            "warming_up": not self.is_warm(),
            "note": None
            if self.is_warm()
            else "snapshot not yet populated; poller is warming up or upstream unreachable",
        }

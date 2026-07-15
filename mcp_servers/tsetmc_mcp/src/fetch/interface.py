"""The single interface every fetch backend implements.

The raw client and the optional 5j9 library both live behind `MarketDataSource`,
so which one is active is a config flip, and a broken upstream endpoint is a
one-method patch rather than a rewrite. Tools and the poller depend ONLY on this
protocol, never on a concrete source.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import ClientType, Instrument, MarketOverview, OrderBookLevel


@runtime_checkable
class MarketDataSource(Protocol):
    name: str

    async def close(self) -> None: ...

    # --- market-wide (polled) ---
    async def market_watch(self) -> list[Instrument]:
        """All instruments' current price snapshot."""

    async def client_type_all(self) -> list[ClientType]:
        """All instruments' حقیقی/حقوقی money-flow snapshot."""

    async def market_overview(self) -> MarketOverview:
        """TEDPIX + equal-weighted index 'at a glance'."""

    # --- per-symbol (on demand) ---
    async def quote(self, ins_code: str) -> Instrument | None:
        """Single-symbol live snapshot (fallback when not in the market snapshot)."""

    async def order_book(self, ins_code: str) -> list[OrderBookLevel]:
        """5-level bid/ask queue (صف خرید/فروش) for one symbol."""

    async def client_type(self, ins_code: str) -> ClientType | None:
        """Single-symbol money flow."""

    async def price_history(self, ins_code: str, days: int) -> list[dict]:
        """Daily OHLCV rows (raw / unadjusted), newest last."""

    async def search(self, query: str) -> list[dict]:
        """Instrument search: [{ins_code, symbol, name, flow}] for a Persian query."""

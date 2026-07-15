"""Optional 5j9/tsetmc-backed source (opt-in accelerator).

Enabled with TSETMC_SOURCE=library on Python >=3.13 after `pip install tsetmc`.
It sits behind the SAME MarketDataSource interface as the raw client, so switching
is a config flip.

Design note (honest): the raw client is the tested, default backend. This class
confirms the 5j9 library is installed and provides the seam where its native async
calls (market_watch.MarketWatch, client_type_all, Instrument.*) are dropped in
per-method. Until a given method has been validated live against 5j9's exact API,
it delegates to the raw client — which is fully tested — so `library` mode is never
LESS correct than `raw`, only progressively faster. Each delegation below is a
labelled single-method upgrade point.
"""

from __future__ import annotations

from ..config import Config
from ..models import ClientType, Instrument, MarketOverview, OrderBookLevel
from .raw_source import RawSource
from .session import Session


class LibrarySource:
    name = "library"

    def __init__(self, cfg: Config, session: Session | None = None):
        try:
            import tsetmc  # noqa: F401  (presence check only)
        except ImportError as exc:  # pragma: no cover - depends on 3.13 env
            raise RuntimeError(
                "TSETMC_SOURCE=library requires the 'tsetmc' package (Python >=3.13). "
                "Install with: pip install 'tsetmc>=3.0'  — or unset TSETMC_SOURCE "
                "to use the built-in raw client (the default)."
            ) from exc
        self._cfg = cfg
        self._raw = RawSource(cfg, session)

    async def close(self) -> None:
        await self._raw.close()

    # Each method is an upgrade point for a native 5j9 call; delegated for now.
    async def market_watch(self) -> list[Instrument]:
        return await self._raw.market_watch()

    async def client_type_all(self) -> list[ClientType]:
        return await self._raw.client_type_all()

    async def market_overview(self) -> MarketOverview:
        return await self._raw.market_overview()

    async def quote(self, ins_code: str) -> Instrument | None:
        return await self._raw.quote(ins_code)

    async def order_book(self, ins_code: str) -> list[OrderBookLevel]:
        return await self._raw.order_book(ins_code)

    async def client_type(self, ins_code: str) -> ClientType | None:
        return await self._raw.client_type(ins_code)

    async def price_history(self, ins_code: str, days: int) -> list[dict]:
        return await self._raw.price_history(ins_code, days)

    async def search(self, query: str) -> list[dict]:
        return await self._raw.search(query)

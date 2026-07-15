"""Raw `cdn.tsetmc.com/api` client — the default, dependency-light backend.

Implements MarketDataSource by calling the modern JSON endpoints directly (see
docs/endpoints.md for the full reference). Each endpoint returns a JSON object
with a single top-level key which we unwrap tolerantly. Parsing of individual
rows is delegated to the models' alias-tolerant `from_api`, so key-name drift in
one endpoint does not break the others.
"""

from __future__ import annotations

from typing import Any

from ..config import Config
from ..jalali import deven_to_date, to_jalali_str
from ..models import ClientType, Instrument, MarketOverview, OrderBookLevel
from ..normalize import normalize_text, to_number
from .session import Session

# TEDPIX (شاخص کل) instrument code — for reference / index history later.
TEDPIX_INS = "32097828820363860"


def _unwrap(data: dict, *keys: str) -> Any:
    """Return the value under the first matching (case-insensitive) key; if the
    object has exactly one key, return that value regardless of name."""
    if not isinstance(data, dict):
        return data
    lower = {k.lower(): v for k, v in data.items()}
    for k in keys:
        if k.lower() in lower:
            return lower[k.lower()]
    if len(data) == 1:
        return next(iter(data.values()))
    return None


def _rows(data: dict, *keys: str) -> list:
    """Unwrap a list endpoint, guaranteeing a list (never a scalar to iterate)."""
    v = _unwrap(data, *keys)
    return v if isinstance(v, list) else []


def _market_watch_query() -> str:
    parts = [
        "market=0",
        "industrialGroup=",
        "showTraded=false",
        "withBestLimits=false",  # order book fetched on demand per symbol
        "hEven=0",
        "RefID=0",
    ]
    for i in range(9):  # paperTypes[0..8] = 1..9 (all instrument paper types)
        parts.append(f"paperTypes%5B{i}%5D={i + 1}")
    return "&".join(parts)


class RawSource:
    name = "raw"

    def __init__(self, cfg: Config, session: Session | None = None):
        self._cfg = cfg
        self._s = session or Session(cfg)

    async def close(self) -> None:
        await self._s.close()

    def _api(self, path: str) -> str:
        return f"{self._cfg.cdn_base}/api/{path.lstrip('/')}"

    # --- market-wide ---
    async def market_watch(self) -> list[Instrument]:
        url = f"{self._api('ClosingPrice/GetMarketWatch')}?{_market_watch_query()}"
        data = await self._s.get_json(url)
        rows = _rows(data, "marketwatch", "marketWatch")
        return [Instrument.from_api(r) for r in rows if isinstance(r, dict)]

    async def client_type_all(self) -> list[ClientType]:
        data = await self._s.get_json(self._api("ClientType/GetClientTypeAll"))
        rows = _rows(data, "clientTypeAllDto", "clientType")
        return [ClientType.from_api(r) for r in rows if isinstance(r, dict)]

    async def market_overview(self) -> MarketOverview:
        data = await self._s.get_json(self._api("MarketData/GetMarketOverview/0"))
        row = _unwrap(data, "marketOverview") or {}
        return MarketOverview.from_api(row if isinstance(row, dict) else {})

    # --- per-symbol ---
    async def quote(self, ins_code: str) -> Instrument | None:
        data = await self._s.get_json(self._api(f"ClosingPrice/GetClosingPriceInfo/{ins_code}"))
        row = _unwrap(data, "closingPriceInfo")
        if not isinstance(row, dict):
            return None
        inst = Instrument.from_api(row)
        if not inst.ins_code:
            inst.ins_code = str(ins_code)
        return inst

    async def order_book(self, ins_code: str) -> list[OrderBookLevel]:
        data = await self._s.get_json(self._api(f"BestLimits/{ins_code}"))
        rows = _rows(data, "bestLimits", "bestLimitsHistory")
        levels = [OrderBookLevel.from_api(r) for r in rows if isinstance(r, dict)]
        levels.sort(key=lambda x: x.level)
        return levels[:5]

    async def client_type(self, ins_code: str) -> ClientType | None:
        data = await self._s.get_json(self._api(f"ClientType/GetClientType/{ins_code}/1/0"))
        row = _unwrap(data, "clientType")
        if isinstance(row, list):
            row = row[0] if row else None
        if not isinstance(row, dict):
            return None
        ct = ClientType.from_api(row)
        if not ct.ins_code:
            ct.ins_code = str(ins_code)
        return ct

    async def price_history(self, ins_code: str, days: int) -> list[dict]:
        top = 0 if days <= 0 else days
        url = self._api(f"ClosingPrice/GetClosingPriceDailyList/{ins_code}/{top}")
        data = await self._s.get_json(url)
        rows = _rows(data, "closingPriceDaily")
        out: list[dict] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            d = deven_to_date(r.get("dEven") or r.get("deven"))
            out.append(
                {
                    "date_gregorian": d.isoformat() if d else None,
                    "date_jalali": to_jalali_str(d) if d else None,
                    "open": to_number(r.get("priceFirst")),
                    "high": to_number(r.get("priceMax")),
                    "low": to_number(r.get("priceMin")),
                    "close": to_number(r.get("pClosing")),
                    "last": to_number(r.get("pDrCotVal")),
                    "yesterday": to_number(r.get("priceYesterday")),
                    "volume": to_number(r.get("qTotTran5J")),
                    "value": to_number(r.get("qTotCap")),
                    "count": to_number(r.get("zTotTran")),
                }
            )
        out.sort(key=lambda x: x["date_gregorian"] or "")
        return out

    async def search(self, query: str) -> list[dict]:
        data = await self._s.get_json(self._api(f"Instrument/GetInstrumentSearch/{query}"))
        rows = _rows(data, "instrumentSearch")
        out = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            out.append(
                {
                    "ins_code": str(r.get("insCode") or ""),
                    "symbol": normalize_text(r.get("lVal18AFC")),
                    "name": normalize_text(r.get("lVal30")),
                    "flow": to_number(r.get("flow")),
                }
            )
        return out

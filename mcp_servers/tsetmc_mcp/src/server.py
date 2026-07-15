"""FastMCP server: exposes the TSETMC tools to Claude Code over stdio.

Each tool is a thin async wrapper over Service. The background poller is started
in the lifespan so the snapshot warms as soon as Claude Code spawns the server,
and is stopped cleanly on shutdown. NOTHING here prints to stdout — that channel
is reserved for MCP's JSON-RPC; logs go to stderr.
"""

from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager

from fastmcp import FastMCP

from .calendar_tsec import market_status
from .config import load_config
from .fetch import make_source
from .poller import Poller
from .service import Service
from .snapshot import Snapshot

cfg = load_config()
snapshot = Snapshot(cfg)
source = make_source(cfg)
service = Service(cfg, source, snapshot)
poller = Poller(cfg, source, snapshot)


@asynccontextmanager
async def lifespan(_server: FastMCP):
    poller.start()
    try:
        yield {}
    finally:
        # Ensure the aiohttp session is closed even if stopping the poller raises.
        try:
            await poller.stop()
        finally:
            await source.close()


mcp = FastMCP("tsetmc", lifespan=lifespan)


@mcp.tool()
async def search_symbol(query: str, limit: int = 10) -> dict:
    """Resolve a Tehran-exchange نماد (symbol) to its instrument code (insCode).

    Accepts Persian text; Arabic ي/ك and Persian/Arabic digits are normalized
    automatically. Use this first when you only know the symbol name.
    Returns {results:[{ins_code, symbol, name}], meta}.
    """
    return await service.search_symbol(query, limit)


@mcp.tool()
async def get_quote(symbol: str) -> dict:
    """Live price snapshot for one symbol (نماد or insCode).

    Returns last/closing/open/high/low prices, % change vs. yesterday, traded
    volume & value, EPS, P/E and base volume. Prices are in Rial. Served from the
    in-memory market snapshot; check meta.market_open and meta.staleness_seconds
    to know how fresh it is.
    """
    return await service.get_quote(symbol)


@mcp.tool()
async def get_order_book(symbol: str) -> dict:
    """Live 5-level order book (صف خرید/فروش) for one symbol.

    Each level has bid (تقاضا) and ask (عرضه) price, volume and order count. A
    heavy imbalance with an empty opposite side indicates a buy/sell queue. Fetched
    live per call (5 levels is the maximum depth TSETMC exposes).
    """
    return await service.get_order_book(symbol)


@mcp.tool()
async def get_money_flow(symbol: str) -> dict:
    """Individual-vs-institutional money flow (حقیقی/حقوقی) for one symbol.

    Returns buy/sell volumes and counts split into individual (I / حقیقی) and legal
    (N / حقوقی), plus legal_net_volume (positive = institutional accumulation).
    Useful for 'smart money' (پول هوشمند) reads.
    """
    return await service.get_money_flow(symbol)


@mcp.tool()
def get_market_watch(
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
    """Filtered/sorted view of the whole market (دیده‌بان) from the live snapshot.

    ALWAYS filtered and limited so it never dumps ~700 rows. sort_by ∈
    {value, volume, pct_change, last, count}. Optional filters: min_pct/max_pct
    (percent change), min_volume, min_value, flow (1=Bourse, 2=Farabourse, 4=پایه),
    symbol_contains. fields projects specific columns (default is a compact set).
    Returns {rows, returned, matched, truncated, meta}.
    """
    return service.get_market_watch(
        limit=limit,
        sort_by=sort_by,
        descending=descending,
        min_pct=min_pct,
        max_pct=max_pct,
        min_volume=min_volume,
        min_value=min_value,
        flow=flow,
        symbol_contains=symbol_contains,
        fields=fields,
    )


@mcp.tool()
def screen(kind: str = "top_gainers", limit: int | None = None) -> dict:
    """Prebuilt market screens over the live snapshot.

    kind ∈ {top_gainers, top_losers, most_active_value, most_active_volume,
    most_active_trades, market_breadth}. market_breadth returns advancers/
    decliners/unchanged counts; the others return a ranked, limited list.
    """
    return service.screen(kind=kind, limit=limit)


@mcp.tool()
async def get_index_overview() -> dict:
    """Market 'at a glance' (در یک نگاه): TEDPIX (شاخص کل) and the equal-weighted
    index — last value and change — plus total market value and state.
    """
    return await service.get_index_overview()


@mcp.tool()
async def get_price_history(symbol: str, days: int = 30, save_csv: bool = False) -> dict:
    """Daily OHLCV history for one symbol (raw / unadjusted), newest last.

    days<=0 means the full available history. Large pulls (or save_csv=True) are
    written to a CSV file and the response returns {file_path, summary, sample}
    instead of every row, to protect the context window. Prices in Rial.
    """
    return await service.get_price_history(symbol, days=days, save_csv=save_csv)


@mcp.tool()
def market_status_tool() -> dict:
    """Is the Tehran market open right now? Returns open/trading-day status, the
    current Tehran time, the session window, and the current snapshot freshness."""
    return {"status": market_status(cfg), "meta": snapshot.meta()}


@mcp.tool()
def describe_fields() -> dict:
    """Reference: what each field means and its units. Call once; don't repeat."""
    return {
        "units": {
            "prices": "Rial (ریال). Divide by 10 for Toman.",
            "volume": "number of shares traded",
            "value": "traded value in Rial",
            "pct_change": "percent change of last price vs. yesterday's close",
        },
        "instrument_fields": {
            "last": "last trade price (pl / pDrCotVal)",
            "close": "final/closing weighted price (pc / pClosing)",
            "yesterday": "previous session close (py)",
            "open": "first trade price (pf)",
            "low/high": "session min/max (pmin/pmax)",
            "count": "number of trades (tno)",
            "volume": "traded volume (tvol)",
            "value": "traded value (tval)",
            "base_volume": "حجم مبنا (baseVol)",
            "eps": "earnings per share",
            "pe": "price/earnings",
            "flow": "market: 1=Bourse, 2=Farabourse/OTC, 4=بازار پایه",
        },
        "money_flow_fields": {
            "buy_i_volume/sell_i_volume": "individual (حقیقی) buy/sell volume",
            "buy_n_volume/sell_n_volume": "legal/institutional (حقوقی) buy/sell volume",
            "legal_net_volume": "legal buy minus legal sell (positive = accumulation)",
        },
        "meta_fields": {
            "market_open": "whether Tehran market is currently in session",
            "staleness_seconds": "age of the snapshot the data was served from",
            "upstream_reachable": "whether the last poll reached TSETMC",
            "source": "backend:served — e.g. raw:snapshot or raw:live",
        },
    }


@mcp.tool()
async def run_filter(
    expression: str,
    limit: int = 20,
    enrich_limit: int = 30,
    save_as: str | None = None,
    description: str = "",
) -> dict:
    """Run a custom stock filter over the live market and return matching symbols.

    `expression` is a boolean condition over a symbol's fields. Accepts TSETMC filter
    syntax — e.g. `(ct).Buy_I_Volume-(ct).Sell_I_Volume>0 && (plp)>0` — OR friendly
    aliases — e.g. `net_individual > 0 and change_pct > 0`. Call filter_help() first to
    see all variables (price/volume/eps/pe, حقیقی-حقوقی ct_*, order-book, buy_queue()).
    Order-book/صف filters enrich a shortlist on demand (capped by enrich_limit). Pass
    `save_as` to store the filter under a name for reuse. Returns {rows, matched,
    returned, normalized, tier, meta}.
    """
    return await service.run_filter(
        expression, limit=limit, enrich_limit=enrich_limit, save_as=save_as, description=description
    )


@mcp.tool()
async def run_saved_filter(name: str, limit: int = 20, enrich_limit: int = 30) -> dict:
    """Run a previously saved filter OR a built-in preset by name.

    Presets include: up_liquid, net_individual_inflow, buyer_power_2x, code_to_code,
    institutional_accumulation, volume_spike, smart_money_lite, buy_queue, sell_queue.
    Unknown names return the list of available presets + saved filters.
    """
    return await service.run_saved_filter(name, limit=limit, enrich_limit=enrich_limit)


@mcp.tool()
def filter_help() -> dict:
    """Reference for writing filters: all variables (with meanings), operators,
    functions, the buy_queue()/sell_queue() sugar, built-in presets, and the user's
    saved filters. Call this before writing a filter so it uses valid names."""
    return service.filter_help()


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    mcp.run(
        transport="http",
        host="0.0.0.0",
        port=8000,
    )

if __name__ == "__main__":
    main()

"""The filter variable registry.

Maps every filter name (both the TSETMC token like `pl`/`tvol`/`ct_buy_i_vol` and a
friendly alias like `last`/`volume`) to a value pulled from a symbol's snapshot row.
Missing numeric values become NaN so a comparison on them is simply False (the row
does not match) rather than raising. Classifies names into snapshot-available,
order-book (needs on-demand enrichment), and unsupported (rejected with a message).
"""

from __future__ import annotations

import math

from ..models import ClientType, Instrument, OrderBookLevel

NAN = math.nan


def _f(v) -> float:
    """Number or NaN. None/blank -> NaN so comparisons yield False, never crash."""
    if v is None:
        return NAN
    if isinstance(v, bool):
        return 1.0 if v else 0.0
    if isinstance(v, (int, float)):
        return float(v)
    return NAN


def _safe_div(a: float, b: float) -> float:
    if _f(b) in (0, 0.0) or math.isnan(_f(a)) or math.isnan(_f(b)):
        return NAN
    return a / b


# ---- name documentation (also drives filter_help) ----
VARIABLE_DOCS: dict[str, str] = {
    # prices
    "pl / last": "last traded price",
    "pc / close": "closing (weighted) price",
    "py / yesterday": "yesterday's close (basis for % change)",
    "pf / open": "opening trade",
    "pmax / high": "day high",
    "pmin / low": "day low",
    # change
    "plp / change_pct": "% change of last vs yesterday",
    "pcp / close_change_pct": "% change of close vs yesterday",
    "plc": "last − yesterday (Rial)",
    "pcc": "close − yesterday (Rial)",
    # volume
    "tvol / volume": "traded volume (shares)",
    "tval / value": "traded value (Rial)",
    "tno / trade_count": "number of trades",
    "bvol / base_volume": "base volume (حجم مبنا)",
    # fundamentals / identity
    "eps": "earnings per share",
    "pe": "price/earnings",
    "symbol / l18": "نماد (string)",
    "name / l30": "company name (string)",
    "flow": "market (1=Bourse,2=Farabourse,4=پایه)",
    # client type (حقیقی/حقوقی)
    "ct_buy_i_vol / ct_sell_i_vol": "individual (حقیقی) buy/sell volume",
    "ct_buy_count_i / ct_sell_count_i": "individual buyer/seller count",
    "ct_buy_n_vol / ct_sell_n_vol": "legal (حقوقی) buy/sell volume",
    "ct_buy_count_n / ct_sell_count_n": "legal buyer/seller count",
    "net_individual": "ct_buy_i_vol − ct_sell_i_vol (net حقیقی inflow)",
    "percap_buy / percap_sell": "per-capita individual buy/sell (سرانه)",
    "buyer_power": "percap_buy / percap_sell (قدرت خرید حقیقی)",
    # order book (enriched, on demand)
    "pd1..pd5 / qd1..qd5 / zd1..zd5": "bid (تقاضا) price/volume/order-count, levels 1-5",
    "po1..po5 / qo1..qo5 / zo1..zo5": "ask (عرضه) price/volume/order-count, levels 1-5",
    "buy_queue() / sell_queue()": "sugar: symbol locked in a buy/sell queue (صف)",
}

# Names that resolve from the market-wide snapshot + client-type poll.
_ORDERBOOK_NAMES: set[str] = set()
for _side in ("d", "o"):
    for _lvl in range(1, 6):
        for _kind in ("p", "q", "z"):
            _ORDERBOOK_NAMES.add(f"{_kind}{_side}{_lvl}")
ORDERBOOK_NAMES = frozenset(_ORDERBOOK_NAMES)

# Known-but-unsupported names -> a clear message instead of "unknown variable".
UNSUPPORTED: dict[str, str] = {
    "mv": "market cap not available (needs shares outstanding)",
    "market_cap": "market cap not available (needs shares outstanding)",
    "z": "shares outstanding not in the snapshot",
    "shares_outstanding": "shares outstanding not in the snapshot",
    "cs": "sector code needs instrument-metadata enrichment (not in v1)",
    "sector": "sector code needs instrument-metadata enrichment (not in v1)",
    "nav": "fund NAV not in the snapshot",
    "tmax": "day price-ceiling not in the snapshot — use buy_queue() for صف خرید",
    "tmin": "day price-floor not in the snapshot — use sell_queue() for صف فروش",
}


def build_row(inst: Instrument, ct: ClientType | None) -> dict:
    """Build the name->value dict for one instrument (snapshot + client-type)."""
    last, close, y = _f(inst.last), _f(inst.close), _f(inst.yesterday)
    pcp = (
        _safe_div((close - y), y) * 100
        if not math.isnan(close) and not math.isnan(y) and y != 0
        else NAN
    )
    bi, ci = _f(ct.buy_i_volume) if ct else NAN, _f(ct.buy_i_count) if ct else NAN
    si, csi = _f(ct.sell_i_volume) if ct else NAN, _f(ct.sell_i_count) if ct else NAN
    percap_buy, percap_sell = _safe_div(bi, ci), _safe_div(si, csi)
    row = {
        # prices
        "pl": last,
        "last": last,
        "pc": close,
        "close": close,
        "py": y,
        "yesterday": y,
        "pf": _f(inst.open),
        "open": _f(inst.open),
        "pmax": _f(inst.high),
        "high": _f(inst.high),
        "pmin": _f(inst.low),
        "low": _f(inst.low),
        # change
        "plp": _f(inst.pct_change),
        "change_pct": _f(inst.pct_change),
        "pcp": pcp,
        "close_change_pct": pcp,
        "plc": (last - y) if not math.isnan(last) and not math.isnan(y) else NAN,
        "pcc": (close - y) if not math.isnan(close) and not math.isnan(y) else NAN,
        # volume
        "tvol": _f(inst.volume),
        "volume": _f(inst.volume),
        "tval": _f(inst.value),
        "value": _f(inst.value),
        "tno": _f(inst.count),
        "trade_count": _f(inst.count),
        "bvol": _f(inst.base_volume),
        "base_volume": _f(inst.base_volume),
        # fundamentals / identity
        "eps": _f(inst.eps),
        "pe": _f(inst.pe),
        "flow": _f(inst.flow),
        "symbol": inst.symbol or "",
        "l18": inst.symbol or "",
        "name": inst.name or "",
        "l30": inst.name or "",
        # client type
        "ct_buy_i_vol": bi,
        "ct_buy_count_i": ci,
        "ct_sell_i_vol": si,
        "ct_sell_count_i": csi,
        "ct_buy_n_vol": _f(ct.buy_n_volume) if ct else NAN,
        "ct_sell_n_vol": _f(ct.sell_n_volume) if ct else NAN,
        "ct_buy_count_n": _f(ct.buy_n_count) if ct else NAN,
        "ct_sell_count_n": _f(ct.sell_n_count) if ct else NAN,
        "net_individual": (bi - si) if not math.isnan(bi) and not math.isnan(si) else NAN,
        "percap_buy": percap_buy,
        "percap_sell": percap_sell,
        "buyer_power": _safe_div(percap_buy, percap_sell),
    }
    return row


def augment_orderbook(row: dict, levels: list[OrderBookLevel]) -> None:
    """Add pd/qd/zd/po/qo/zo names from a symbol's order book (levels 1-5)."""
    by_level = {lv.level: lv for lv in levels}
    for n in range(1, 6):
        lv = by_level.get(n)
        # Absent level -> NaN (consistent with the rest of the engine's "missing ==
        # no-match"), so a raw `qo1 == 0` never fires on a symbol with no order book.
        row[f"pd{n}"] = _f(lv.bid_price) if lv else NAN
        row[f"qd{n}"] = _f(lv.bid_volume) if lv else NAN
        row[f"zd{n}"] = _f(lv.bid_count) if lv else NAN
        row[f"po{n}"] = _f(lv.ask_price) if lv else NAN
        row[f"qo{n}"] = _f(lv.ask_volume) if lv else NAN
        row[f"zo{n}"] = _f(lv.ask_count) if lv else NAN


# All names available (snapshot + client-type + order-book). Built from a sample row.
_SAMPLE = build_row(Instrument(ins_code="0"), None)
augment_orderbook(_SAMPLE, [])
ALLOWED_NAMES = frozenset(_SAMPLE.keys())
SNAPSHOT_NAMES = frozenset(k for k in ALLOWED_NAMES if k not in ORDERBOOK_NAMES)

"""Normalized data models shared by every fetch source and tool.

TSETMC's JSON uses terse, sometimes-inconsistent key names across its modern and
legacy endpoints, and the exact market-watch key spelling is not fully documented.
Every model therefore parses via `_pick`, which tries a list of known aliases and
tolerates missing values — so a source can feed us either naming and the same
normalized object comes out. Unknown/extra keys are ignored, never fatal.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from .normalize import normalize_text, to_number


def _pick(d: dict, aliases: tuple[str, ...], default=None):
    for a in aliases:
        if a in d and d[a] not in (None, ""):
            return d[a]
    # Case-insensitive second pass (legacy vs modern casing).
    lower = {k.lower(): v for k, v in d.items()}
    for a in aliases:
        v = lower.get(a.lower())
        if v not in (None, ""):
            return v
    return default


def _num(d: dict, aliases: tuple[str, ...]):
    return to_number(_pick(d, aliases))


def _price(d: dict, aliases: tuple[str, ...]):
    """Like _num, but a price of 0 means 'no trade / not applicable' on TSETMC,
    so it is returned as None (prevents fake -100% moves off-session)."""
    v = to_number(_pick(d, aliases))
    return None if v in (0, 0.0) else v


@dataclass
class Instrument:
    """One symbol's live price snapshot (prices in Rial)."""

    ins_code: str
    symbol: str = ""  # نماد (l18)
    name: str = ""  # company name (l30)
    last: float | None = None  # last trade price (pl / pDrCotVal)
    close: float | None = None  # final/closing price (pc / pClosing)
    yesterday: float | None = None  # previous close (py)
    open: float | None = None  # first trade (pf)
    low: float | None = None  # pmin
    high: float | None = None  # pmax
    count: int | None = None  # number of trades (tno / zTotTran)
    volume: int | None = None  # traded volume (tvol / qTotTran5J)
    value: int | None = None  # traded value (tval / qTotCap)
    base_volume: int | None = None  # حجم مبنا (baseVol)
    eps: float | None = None
    pe: float | None = None
    flow: int | None = None  # market flow (1 Bourse, 2 Farabourse, ...)
    state: str | None = None  # trading state code/title if present

    @property
    def pct_change(self) -> float | None:
        """Percent change of last vs. yesterday's close."""
        if self.last is None or not self.yesterday:
            return None
        return round((self.last - self.yesterday) / self.yesterday * 100, 2)

    @classmethod
    def from_api(cls, d: dict) -> Instrument:
        ins = _pick(d, ("insCode", "InsCode", "ins_code", "code"))
        return cls(
            ins_code=str(ins) if ins is not None else "",
            symbol=normalize_text(_pick(d, ("lVal18AFC", "lva", "l18", "symbol"))),
            name=normalize_text(_pick(d, ("lVal30", "lvc", "l30", "name", "title"))),
            # Prices: 0 == no-trade on TSETMC -> None. NOTE on low/high: in the
            # market-watch feed pmn/pmx are the *traded* low/high while pMin/pMax
            # (capital) are the price-limit thresholds — so the short "pmin/pmax"
            # aliases are deliberately omitted to avoid a case-insensitive collision
            # with pMin/pMax. Per-symbol endpoints use the full priceMin/priceMax.
            last=_price(d, ("pDrCotVal", "pl", "pdv", "last")),
            close=_price(d, ("pClosing", "pc", "pcl", "closing")),
            yesterday=_num(d, ("priceYesterday", "py", "yesterday")),
            open=_price(d, ("priceFirst", "pf", "pfirst", "open")),
            low=_price(d, ("priceMin", "pmn")),
            high=_price(d, ("priceMax", "pmx")),
            count=_num(d, ("zTotTran", "tno", "ztottran", "count")),
            volume=_num(d, ("qTotTran5J", "tvol", "qtottran5j", "volume")),
            value=_num(d, ("qTotCap", "tval", "qtotcap", "value")),
            base_volume=_num(d, ("baseVol", "bvol", "basevol")),
            eps=_num(d, ("estimatedEPS", "eps", "estimated_eps")),
            pe=_num(d, ("pe", "priceEarnings")),
            flow=_num(d, ("flow", "Flow")),
            state=_pick(d, ("cEtavalTitle", "instrumentState", "state", "cEtaval")),
        )

    def to_dict(self) -> dict:
        out = asdict(self)
        out["pct_change"] = self.pct_change
        return out


@dataclass
class OrderBookLevel:
    level: int
    bid_price: float | None = None  # pMeDem (تقاضا)
    bid_volume: int | None = None  # qTitMeDem
    bid_count: int | None = None  # zOrdMeDem
    ask_price: float | None = None  # pMeOf (عرضه)
    ask_volume: int | None = None  # qTitMeOf
    ask_count: int | None = None  # zOrdMeOf

    @classmethod
    def from_api(cls, d: dict) -> OrderBookLevel:
        return cls(
            level=int(to_number(_pick(d, ("number", "n", "level"))) or 0),
            bid_price=_num(d, ("pMeDem", "pd", "bid_price")),
            bid_volume=_num(d, ("qTitMeDem", "qd", "bid_volume")),
            bid_count=_num(d, ("zOrdMeDem", "zd", "bid_count")),
            ask_price=_num(d, ("pMeOf", "po", "ask_price")),
            ask_volume=_num(d, ("qTitMeOf", "qo", "ask_volume")),
            ask_count=_num(d, ("zOrdMeOf", "zo", "ask_count")),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ClientType:
    """حقیقی/حقوقی (individual 'I' vs legal 'N') money flow for one symbol."""

    ins_code: str
    buy_i_volume: int | None = None
    buy_n_volume: int | None = None
    sell_i_volume: int | None = None
    sell_n_volume: int | None = None
    buy_i_count: int | None = None
    buy_n_count: int | None = None
    sell_i_count: int | None = None
    sell_n_count: int | None = None

    @property
    def legal_net_volume(self) -> int | None:
        """Net legal (حقوقی) buy volume — positive = legal accumulation."""
        if self.buy_n_volume is None or self.sell_n_volume is None:
            return None
        return int(self.buy_n_volume - self.sell_n_volume)

    @classmethod
    def from_api(cls, d: dict) -> ClientType:
        ins = _pick(d, ("insCode", "InsCode", "ins_code"))
        return cls(
            ins_code=str(ins) if ins is not None else "",
            buy_i_volume=_num(d, ("buy_I_Volume", "buy_i_volume", "Buy_I_Volume")),
            buy_n_volume=_num(d, ("buy_N_Volume", "buy_n_volume", "Buy_N_Volume")),
            sell_i_volume=_num(d, ("sell_I_Volume", "sell_i_volume", "Sell_I_Volume")),
            sell_n_volume=_num(d, ("sell_N_Volume", "sell_n_volume", "Sell_N_Volume")),
            buy_i_count=_num(d, ("buy_CountI", "buy_count_i", "Buy_CountI")),
            buy_n_count=_num(d, ("buy_CountN", "buy_count_n", "Buy_CountN")),
            sell_i_count=_num(d, ("sell_CountI", "sell_count_i", "Sell_CountI")),
            sell_n_count=_num(d, ("sell_CountN", "sell_count_n", "Sell_CountN")),
        )

    def to_dict(self) -> dict:
        out = asdict(self)
        out["legal_net_volume"] = self.legal_net_volume
        return out


@dataclass
class MarketOverview:
    index_value: float | None = None
    index_change: float | None = None
    ew_index_value: float | None = None  # equal-weighted (هم‌وزن)
    ew_index_change: float | None = None
    market_value: int | None = None
    state: str | None = None

    @classmethod
    def from_api(cls, d: dict) -> MarketOverview:
        return cls(
            index_value=_num(d, ("indexLastValue", "indexlastvalue", "index")),
            index_change=_num(d, ("indexChange", "indexchange")),
            ew_index_value=_num(d, ("indexEqualWeightedLastValue", "ewindex")),
            ew_index_change=_num(d, ("indexEqualWeightedChange", "ewindexchange")),
            market_value=_num(d, ("marketValue", "marketvalue")),
            state=_pick(d, ("marketState", "state")),
        )

    def to_dict(self) -> dict:
        return asdict(self)

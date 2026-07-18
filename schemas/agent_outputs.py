from typing import Literal, Union, Optional
from pydantic import BaseModel, Field, model_validator

#-----------------------------------------------------------NewsSignal

class MaterialEvent(BaseModel):
    event: str
    reason: str

class NewsSignal(BaseModel):
    """Output of the News & Sentiment agent."""
    symbol: str
    as_of: str  # ISO timestamp used for before_ts
    sentiment_score: float = Field(..., ge=-1, le=1)
    key_events: list[MaterialEvent] = Field(default_factory=list, max_length=4)
    material_article_count: int = Field(..., ge=0)
    confidence: float = Field(..., ge=0, le=1)

#-----------------------------------------------------------DomesticMarketSignal

class MaterialObservation(BaseModel):
    observation: str
    reason: str

class DomesticMarketSignal(BaseModel):
    """Output of the Domestic (TSE/TSETMC) Market Agent."""
    symbol: str
    instrument_code: str | None = None   # resolved via search_symbol if input was a Persian name
    as_of: str                            # ISO timestamp
    market_open: bool
    queue_status: Literal["NONE", "BUY_QUEUE", "SELL_QUEUE"] = "NONE"
    money_flow_signal: Literal["INSTITUTIONAL_NET_BUY", "INSTITUTIONAL_NET_SELL", "NEUTRAL"]
    sentiment_score: float = Field(..., ge=-1, le=1)
    key_observations: list[MaterialObservation] = Field(default_factory=list, max_length=4)
    confidence: float = Field(..., ge=0, le=1)
#-----------------------------------------------------------ForeignMarketSignal

class KeyIndicator(BaseModel):
    name: str      # e.g. "RSI(14)", "MACD cross", "Bollinger %B"
    reading: str   # e.g. "oversold at 28", "bullish golden cross"

class BacktestSummary(BaseModel):
    strategy: str
    total_return_pct: float
    sharpe_ratio: float
    win_rate_pct: float
    robustness_verdict: Literal["ROBUST", "MODERATE", "WEAK", "OVERFITTED"] | None = None

class ForeignMarketSignal(BaseModel):
    """Output of the Foreign/Global Market Technical Agent."""
    symbol: str
    exchange: str | None = None          # e.g. NASDAQ, BINANCE
    as_of: str                            # ISO timestamp
    market_state: Literal["PRE", "REGULAR", "POST", "CLOSED"]
    verdict: Literal["BUY", "SELL", "HOLD"]
    signal_score: float = Field(..., ge=-1, le=1)
    key_indicators: list[KeyIndicator] = Field(default_factory=list, max_length=4)
    confidence: float = Field(..., ge=0, le=1)
    backtest_summary: BacktestSummary | None = None  # only if explicitly requested

#-----------------------------------------------------------
class OrchestratorSignal(BaseModel):
    symbol: str
    market: Literal["FOREIGN", "DOMESTIC", "BOTH"] | None = None
    as_of: str
    news_signal: Optional["NewsSignal"] = None
    foreign_signal: Optional["ForeignMarketSignal"] = None
    domestic_signal: Optional["DomesticMarketSignal"] = None
    agreement: Literal["AGREE", "CONFLICT", "PARTIAL"]
    overall_score: float = Field(..., ge=-1, le=1)
    overall_confidence: float = Field(..., ge=0, le=1)
 
    rationale: str = Field(
        ...,
        description=(
            "Short 1-3 sentence executive summary of the verdict. Not the place "
            "for the full walkthrough -- see detailed_reasoning."
        ),
    )
    detailed_reasoning: str = Field(
        ...,
        description=(
            "Full analyst-note-style narrative covering, per sub-agent called: its "
            "score and the substance behind it; then cross-agent agreement/"
            "divergence; then the weighting scheme applied and why; then how that "
            "synthesis produced overall_score/overall_verdict/overall_confidence. "
            "Must name every sub-agent actually called and must not merely restate "
            "rationale."
        ),
    )
 
    @model_validator(mode="after")
    def infer_market_if_missing(self):
        if self.market is None:
            has_foreign = self.foreign_signal is not None
            has_domestic = self.domestic_signal is not None
            if has_foreign and has_domestic:
                self.market = "BOTH"
            elif has_domestic:
                self.market = "DOMESTIC"
            elif has_foreign:
                self.market = "FOREIGN"
            else:
                raise ValueError("Cannot infer market: no sub-signal populated.")
        return self



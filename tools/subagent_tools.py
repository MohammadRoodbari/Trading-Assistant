import json
from datetime import datetime, timezone

from langchain_core.tools import tool

from agents.domestic_market_agent import build_domestic_market_agent
from agents.foreign_market_agent import build_foreign_market_agent
from agents.news_agent import build_news_agent


class SubAgents:
    """Sub-agent graphs are built once and reused across all orchestrator calls."""

    def __init__(self):
        self.domestic_market_agent = None
        self.foreign_market_agent = None
        self.news_agent = None

    async def setup(self) -> "SubAgents":
        self.domestic_market_agent = await build_domestic_market_agent()
        self.foreign_market_agent = await build_foreign_market_agent()
        self.news_agent = await build_news_agent()
        return self


def _dump(structured_obj) -> str:
    return json.dumps(structured_obj.model_dump(), ensure_ascii=False)


def build_subagent_tools(agents: SubAgents):
    @tool
    async def domestic_market_agent(symbol: str) -> str:
        """Analyze a TSETMC (Tehran Stock Exchange) symbol's domestic price/fundamentals
        to judge under/over/fair valuation and liquidity.

        Call this ONLY when the user asks specifically about the domestic/Iranian
        market view of a symbol (e.g. "طلای داخلی چطوره؟"), OR as part of a
        full multi-angle analysis (e.g. a buy/sell decision) where the domestic
        view is one of several signals needed.

        Args:
            symbol: TSETMC ticker/symbol (bare asset/company name, not the full
                user question -- e.g. "طلا", not "وضعیت طلا بازار داخلی چطوره؟").
        """
        try:
            result = await agents.domestic_market_agent.ainvoke(
                {"messages": [{"role": "user", "content": f"symbol: {symbol}"}]}
            )
            return _dump(result["structured_response"])
        except Exception as e:
            return f"domestic_market_agent failed: {e}"

    @tool
    async def foreign_market_agent(symbol: str) -> str:
        """Technical analysis (RSI/MACD/MA) of an international instrument
        (e.g. XAUUSD for gold ounce, XAGUSD for silver ounce, forex pairs).

        Call this ONLY when the user asks specifically about the global/foreign
        price action (e.g. "انس جهانی طلا چطوره؟"), OR as part of a full
        multi-angle analysis.

        Args:
            symbol: International ticker (e.g. XAUUSD) -- bare instrument name,
                not the full user question.
        """
        try:
            result = await agents.foreign_market_agent.ainvoke(
                {"messages": [{"role": "user", "content": f"symbol: {symbol}"}]}
            )
            return _dump(result["structured_response"])
        except Exception as e:
            return f"foreign_market_agent failed: {e}"

    @tool
    async def news_agent(query: str, as_of: str) -> str:
        """Fetch and score recent news/macro sentiment relevant to the user's
        question, bounded by an as_of timestamp (no future leakage).

        Call this whenever the user explicitly asks about news/latest events/
        sentiment, OR as part of a full multi-angle analysis.

        IMPORTANT: `query` must be the user's FULL original question, passed
        verbatim -- not a bare symbol/asset name. news_agent extracts the asset,
        market scope (e.g. domestic vs. global), and intent (e.g. buy/sell framing)
        from the full text itself in order to build a properly targeted news
        search; a bare symbol strips away exactly the context it needs.
        Example: pass "وضعیت طلا بازار داخلی به چه صورته - نظرت در رابطه با خریده
        یا فروش؟" in full, not just "طلا".

        Args:
            query: The user's full original question, verbatim.
            as_of: ISO 8601 timestamp (date AND time) marking the point news
                must not be reasoned about beyond. You must resolve this
                yourself -- if the user gave an explicit date/time, use it;
                otherwise resolve it to the current time. Do not omit this
                or pass an empty value.
        """
        if not as_of or not as_of.strip():
            as_of = datetime.now(timezone.utc).isoformat()

        try:
            result = await agents.news_agent.ainvoke(
                {"messages": [{"role": "user", "content": f"query: {query}\nas_of: {as_of}"}]}
            )
            return _dump(result["structured_response"])
        except Exception as e:
            return f"news_agent failed: {e}"

    return [domestic_market_agent, foreign_market_agent, news_agent]
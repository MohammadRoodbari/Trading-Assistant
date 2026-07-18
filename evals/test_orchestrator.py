
from langchain_core.messages import AIMessage, ToolMessage
import pytest
from agents.orchestrator import build_orchestrator_agent

def extract_tool_trace(result: dict) -> list[dict]:
    """Pulls (tool_name, tool_input) for every sub-agent call, in order."""
    calls = []
    for msg in result["messages"]:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                calls.append({"name": tc["name"], "args": tc["args"]})
    return calls

def extract_signal(result: dict):
    # create_agent puts the pydantic-validated output here when response_format is set
    return result["structured_response"]


_agent = None
async def get_agent():
    global _agent
    if _agent is None:
        _agent = await build_orchestrator_agent()
    return _agent

async def run_orchestrator(query: str) -> dict:
    agent = await get_agent()
    result = await agent.ainvoke({"messages": [("user", query)]})
    return {
        "signal": extract_signal(result),
        "tool_calls": extract_tool_trace(result),
        "raw_messages": result["messages"],
    }





@pytest.mark.asyncio
async def test_dual_listed_commodity_calls_both_markets():
    out = await run_orchestrator("قیمت انس نقره رو تحلیل کن - در یک هفته گذشته قیمت ها به چه صورت بوده")
    called = {c["name"] for c in out["tool_calls"]}
    signal = out["signal"]

    # silver has no explicit market scope -> FOREIGN market agents + news
    assert {"foreign_market_agent", "news_agent"} <= called
    assert signal.market == "FOREIGN"

    # as_of must be identical across every sub-agent call that took one
    as_of_args = {c["args"].get("as_of") for c in out["tool_calls"] if "as_of" in c["args"]}
    assert len(as_of_args) == 1, f"as_of drifted across sub-agents: {as_of_args}"

    # news_agent must receive the FULL original question, not a compressed symbol
    news_call = next(c for c in out["tool_calls"] if c["name"] == "news_agent")
    assert len(news_call["args"].get("query", "")) > len("نقره")  # not just the symbol

    # agreement/confidence consistency rule
    if signal.agreement == "CONFLICT":
        assert signal.overall_confidence <= 0.5

    assert signal.overall_score is not None

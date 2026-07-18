"""
Client wrapper around the tradingview-mcp server
"""
from langchain_mcp_adapters.client import MultiServerMCPClient
from config.settings import settings


_client = MultiServerMCPClient(
    {
        "tradingview": {
            "transport": "streamable_http",
            "url": settings.TRADINGVIEW_MCP_URL,
        }
    }
)


async def get_tools():
    """Fetch the current tool list from tradingview-mcp."""
    return await _client.get_tools()
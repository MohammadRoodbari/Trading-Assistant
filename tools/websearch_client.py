"""
Client wrapper around the websearch-mcp server
"""
from langchain_mcp_adapters.client import MultiServerMCPClient
from config.settings import settings

_client = MultiServerMCPClient(
    {
        "websearch": {
            "transport": "http",
            "url": settings.WEBSEARCH_MCP_URL,
        }
    }
)


async def get_tools():
    """Fetch the current tool list from websearch-mcp."""
    return await _client.get_tools()
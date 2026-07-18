"""
Client wrapper around the tsetmc-mcp server
"""
from langchain_mcp_adapters.client import MultiServerMCPClient
from config.settings import settings
 

_client = MultiServerMCPClient(
    {
        "tsetmc": {
            "transport": "http",
            "url": settings.TSETMC_MCP_URL,
        }
    }
)


async def get_tools():
    """Fetch the current tool list from tsetmc-mcp.
    """
    return await _client.get_tools()
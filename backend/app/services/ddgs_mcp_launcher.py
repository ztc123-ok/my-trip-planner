"""Start the pinned DDGS MCP server with a compatible image request header."""

import asyncio

from ddgs.api_server.mcp import mcp
from ddgs.engines.duckduckgo_images import DuckduckgoImages


def main() -> None:
    # DDGS 9.16.0 sends Connection on HTTP/2 image requests; primp rejects it.
    DuckduckgoImages.headers_update = {
        name: value
        for name, value in DuckduckgoImages.headers_update.items()
        if name.lower() != "connection"
    }
    asyncio.run(mcp.run_stdio_async())


if __name__ == "__main__":
    main()

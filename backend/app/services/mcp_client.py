"""Synchronous adapter for local MCP stdio servers used by the API and graph nodes."""

import asyncio
from datetime import timedelta
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import get_default_environment, stdio_client


class MCPToolClient:
    def __init__(self, server_command: list[str], env: dict[str, str] | None = None):
        self.server_command = server_command
        self.parameters = StdioServerParameters(
            command=server_command[0],
            args=server_command[1:],
            env={**get_default_environment(), **(env or {}), "PYTHONIOENCODING": "utf-8"},
        )
        self.available_tools = asyncio.run(self._list_tools())

    async def _list_tools(self) -> list[str]:
        async with stdio_client(self.parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                names: list[str] = []
                cursor = None
                while True:
                    result = await session.list_tools(cursor=cursor)
                    names.extend(tool.name for tool in result.tools)
                    cursor = result.nextCursor
                    if not cursor:
                        return names

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        async with stdio_client(self.parameters) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    name, arguments, read_timeout_seconds=timedelta(seconds=60)
                )
        texts = [
            block.text for block in result.content
            if getattr(block, "type", None) == "text"
        ]
        if result.isError:
            raise ValueError("\n".join(texts) or f"MCP 工具 {name} 调用失败")
        if result.structuredContent is not None:
            return result.structuredContent
        if len(texts) == 1:
            return texts[0]
        return {"content": [{"type": "text", "text": text} for text in texts]}

    def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        return asyncio.run(self._call_tool(name, arguments))

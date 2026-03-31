"""
MCP client that connects to the packages MCP server via stdio.

Provides the same interface as PackageService so it can be swapped in.
"""
import asyncio
import json
import os
import sys
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class McpPackageService:
    """Package service backed by an MCP server (stdio transport)."""

    def __init__(self):
        self._session: ClientSession | None = None
        self._exit_stack = AsyncExitStack()
        self._loop = asyncio.new_event_loop()

    def connect(self):
        """Connect to the MCP packages server."""
        self._loop.run_until_complete(self._connect())

    async def _connect(self):
        server_path = os.path.join(os.path.dirname(__file__), "mcp_packages_server.py")
        server_params = StdioServerParameters(
            command=sys.executable,
            args=[server_path],
            env={**os.environ},
        )
        stdio_transport = await self._exit_stack.enter_async_context(
            stdio_client(server_params)
        )
        read, write = stdio_transport
        session = await self._exit_stack.enter_async_context(
            ClientSession(read, write)
        )
        await session.initialize()
        self._session = session

        # Discover and log available tools
        tools_response = await session.list_tools()
        print("[MCP Client] Connected. Available tools:")
        for tool in tools_response.tools:
            print(f"  - {tool.name}: {tool.description}")

    def check(self, package_id: str) -> dict:
        """Check package status via MCP."""
        return self._loop.run_until_complete(self._call("check_package", {
            "package_id": package_id,
        }))

    def redirect(self, package_id: str, destination: str, code: str) -> dict:
        """Redirect package via MCP."""
        return self._loop.run_until_complete(self._call("redirect_package", {
            "package_id": package_id,
            "destination": destination,
            "code": code,
        }))

    async def _call(self, tool_name: str, arguments: dict) -> dict:
        if not self._session:
            raise RuntimeError("MCP client not connected. Call connect() first.")
        print(f"  [MCP Client] Calling {tool_name}({arguments})")
        result = await self._session.call_tool(tool_name, arguments)
        # MCP returns content as a list of content blocks
        for block in result.content:
            if hasattr(block, "text"):
                try:
                    return json.loads(block.text)
                except json.JSONDecodeError:
                    return {"result": block.text}
        return {"result": str(result.content)}

    def close(self):
        """Disconnect from MCP server."""
        self._loop.run_until_complete(self._exit_stack.aclose())
        self._loop.close()

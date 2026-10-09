from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from typing import Any


def run_coro_blocking(make_coro: Callable[[], Any]) -> Any:
    box: dict[str, Any] = {}

    def runner() -> None:
        loop = asyncio.new_event_loop()
        try:
            box["value"] = loop.run_until_complete(make_coro())
        except BaseException as exc:  # noqa: BLE001
            box["error"] = exc
        finally:
            loop.close()

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if "error" in box:
        raise box["error"]
    return box["value"]


async def call_fabric_mcp(mcp_url: str, scope: str, question: str) -> str:
    from azure.identity import DefaultAzureCredential
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    token = DefaultAzureCredential().get_token(scope).token
    headers = {"Authorization": f"Bearer {token}"}
    async with streamablehttp_client(mcp_url, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            if not tools.tools:
                raise RuntimeError("Fabric Data Agent MCP endpoint exposed no tools.")
            tool = tools.tools[0]
            properties = (tool.inputSchema or {}).get("properties", {})
            argument_name = next(iter(properties), "userQuestion")
            result = await session.call_tool(tool.name, {argument_name: question})
            parts = [getattr(block, "text", "") for block in result.content]
            return "".join(part for part in parts if part).strip()

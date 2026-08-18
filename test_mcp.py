from __future__ import annotations

import argparse
import asyncio

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def run(url: str) -> None:
    async with streamable_http_client(url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("\nDiscovered MCP tools:")
            for tool in tools.tools:
                schema = getattr(tool, "input_schema", None) or getattr(
                    tool, "inputSchema", {}
                )
                actions = (
                    schema.get("properties", {})
                    .get("action", {})
                    .get("enum", [])
                )
                print(f"  - {tool.name}: {actions}")

            print("\nCalling playlist(action='list')...")
            result = await session.call_tool(
                "playlist",
                arguments={"action": "list"},
            )

            print("\nResult:")
            content = getattr(result, "content", []) or []
            for block in content:
                text = getattr(block, "text", None)
                if text:
                    print(text)

            structured = getattr(result, "structuredContent", None) or getattr(
                result, "structured_content", None
            )
            if structured:
                print("\nStructured result:")
                print(structured)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "url",
        nargs="?",
        default="http://127.0.0.1:8787/mcp",
    )
    args = parser.parse_args()
    asyncio.run(run(args.url))


if __name__ == "__main__":
    main()

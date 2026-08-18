from __future__ import annotations

import argparse
import copy
import os
from typing import Any

import mcp.types as types
import uvicorn
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.server.lowlevel import Server
from mcp.server.transport_security import TransportSecuritySettings


# Prototype scope: personal-data reads only.
# Even though applemusic-mcp itself supports writes, this proxy never advertises
# or accepts them.
READ_ONLY_ACTIONS: dict[str, set[str]] = {
    "playlist": {"list", "folders", "tracks", "search"},
    "library": {
        "search",
        "browse",
        "favorites",
        "recently_played",
        "recently_added",
    },
}

UPSTREAM_COMMAND = os.getenv("APPLE_MUSIC_MCP_COMMAND", "applemusic-mcp")


async def _with_upstream():
    """Create a short-lived stdio connection to the local applemusic-mcp."""
    params = StdioServerParameters(
        command=UPSTREAM_COMMAND,
        args=["serve"],
    )
    return stdio_client(params)


async def _list_upstream_tools() -> list[types.Tool]:
    transport = await _with_upstream()
    async with transport as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return result.tools


async def _call_upstream_tool(name: str, arguments: dict[str, Any]) -> types.CallToolResult:
    transport = await _with_upstream()
    async with transport as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(name, arguments=arguments)


def _get_input_schema(tool: types.Tool) -> dict[str, Any]:
    # Current MCP Python SDK exposes input_schema. Keep a fallback so the
    # prototype also tolerates older compatible Pydantic aliases.
    schema = getattr(tool, "input_schema", None)
    if schema is None:
        schema = getattr(tool, "inputSchema", None)
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}
    return copy.deepcopy(schema)


def _set_input_schema(tool: types.Tool, schema: dict[str, Any]) -> types.Tool:
    cloned = copy.deepcopy(tool)

    if hasattr(cloned, "input_schema"):
        try:
            cloned.input_schema = schema
            return cloned
        except Exception:
            pass

    if hasattr(cloned, "inputSchema"):
        try:
            cloned.inputSchema = schema
            return cloned
        except Exception:
            pass

    # Last-resort reconstruction through Pydantic, preserving the upstream
    # metadata as much as possible.
    if hasattr(cloned, "model_dump") and hasattr(type(cloned), "model_validate"):
        data = cloned.model_dump(by_alias=False)
        data["input_schema"] = schema
        data.pop("inputSchema", None)
        return type(cloned).model_validate(data)

    raise RuntimeError("Could not rewrite upstream MCP tool schema.")


def _read_only_tool(tool: types.Tool) -> types.Tool:
    allowed = READ_ONLY_ACTIONS[tool.name]
    schema = _get_input_schema(tool)

    schema.setdefault("type", "object")
    properties = schema.setdefault("properties", {})

    old_action = properties.get("action", {})
    description = None
    if isinstance(old_action, dict):
        description = old_action.get("description")

    properties["action"] = {
        "type": "string",
        "enum": sorted(allowed),
        "description": description
        or "Read-only Apple Music action permitted by this prototype.",
    }

    required = list(schema.get("required", []))
    if "action" not in required:
        required.append("action")
    schema["required"] = required

    # Make the boundary visible to ChatGPT in the tool description as well.
    cloned = _set_input_schema(tool, schema)
    allowed_text = ", ".join(sorted(allowed))
    base_description = getattr(cloned, "description", "") or ""
    extra = (
        "\n\nREAD-ONLY PROXY: only these actions are allowed: "
        f"{allowed_text}. Mutation actions are rejected server-side."
    )
    try:
        cloned.description = base_description + extra
    except Exception:
        pass
    return cloned


async def handle_list_tools(ctx, params) -> types.ListToolsResult:
    upstream = await _list_upstream_tools()

    exposed: list[types.Tool] = []
    for tool in upstream:
        if tool.name in READ_ONLY_ACTIONS:
            exposed.append(_read_only_tool(tool))

    return types.ListToolsResult(tools=exposed)


async def handle_call_tool(ctx, params) -> types.CallToolResult:
    name = params.name
    arguments = dict(params.arguments or {})
    action = arguments.get("action")

    if name not in READ_ONLY_ACTIONS:
        raise ValueError(
            f"Tool '{name}' is not exposed by the read-only Apple Music proxy."
        )

    if action not in READ_ONLY_ACTIONS[name]:
        allowed = ", ".join(sorted(READ_ONLY_ACTIONS[name]))
        raise ValueError(
            f"Action '{action}' is blocked. Allowed read-only actions for "
            f"'{name}': {allowed}."
        )

    result = await _call_upstream_tool(name, arguments)

    # Preserve the upstream MCP result exactly: text, structured content,
    # error state, and metadata all pass through.
    return result


server = Server(
    "Apple Music Read-Only Remote Proxy",
    version="0.1.0",
    instructions=(
        "Read-only access to the user's personal Apple Music playlists and library. "
        "Use playlist(action='list') to discover playlists, then "
        "playlist(action='tracks', ...) to inspect a selected playlist. "
        "Never invent personal library contents."
    ),
    on_list_tools=handle_list_tools,
    on_call_tool=handle_call_tool,
)


def build_app(public_host: str | None):
    allowed_hosts = [
        "127.0.0.1:*",
        "localhost:*",
        "[::1]:*",
    ]
    allowed_origins = [
        "http://127.0.0.1:*",
        "http://localhost:*",
        "http://[::1]:*",
    ]

    if public_host:
        # Cloudflare forwards the original public Host header.
        allowed_hosts.extend([public_host, f"{public_host}:*"])
        allowed_origins.extend(
            [
                f"https://{public_host}",
                f"https://{public_host}:*",
            ]
        )

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=allowed_hosts,
        allowed_origins=allowed_origins,
    )

    return server.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        transport_security=security,
        host="127.0.0.1",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Expose local applemusic-mcp as a read-only Streamable HTTP MCP server."
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Local bind host. Keep 127.0.0.1 when using Cloudflare Tunnel.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8787,
        help="Local port. Default: 8787.",
    )
    parser.add_argument(
        "--public-host",
        default=None,
        help=(
            "Public hostname used by the tunnel, without https://. "
            "Example: random-words.trycloudflare.com"
        ),
    )
    args = parser.parse_args()

    app = build_app(args.public_host)

    print()
    print("Apple Music Remote MCP prototype")
    print("--------------------------------")
    print(f"Local MCP URL:  http://{args.host}:{args.port}/mcp")
    if args.public_host:
        print(f"Public MCP URL: https://{args.public_host}/mcp")
    else:
        print("Public host:     not configured")
    print("Exposed tools:   playlist, library (read-only)")
    print()

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()

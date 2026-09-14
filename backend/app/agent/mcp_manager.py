"""Manages connected MCP servers and exposes their tools to the agent.

Connections are opened once (at app startup or when a server is added) and kept
alive on ``app.state``. Each remote tool is wrapped as a normal :class:`ToolSpec`
so the agent treats MCP tools identically to built-in and plugin tools.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from .mcp_client import MCPClient, MCPTool
from .tools import ToolContext, ToolSpec

logger = logging.getLogger("localmind.agent.mcp")


@dataclass(slots=True)
class MCPServerConfig:
    name: str
    command: str
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ConnectedServer:
    config: MCPServerConfig
    client: MCPClient | None
    tools: list[MCPTool] = field(default_factory=list)
    error: str | None = None


def _sanitize(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
    return cleaned[:60] or "tool"


class MCPManager:
    def __init__(self, require_approval: bool = True) -> None:
        self._servers: dict[str, ConnectedServer] = {}
        self._require_approval = require_approval

    async def connect(self, config: MCPServerConfig) -> ConnectedServer:
        # Replace any existing connection with the same name.
        await self.disconnect(config.name)
        client = MCPClient()
        try:
            await client.connect(config.command, config.args, config.env)
            tools = await client.list_tools()
            server = ConnectedServer(config=config, client=client, tools=tools)
            logger.info("MCP '%s' connected with %d tools", config.name, len(tools))
        except Exception as exc:
            await client.aclose()
            server = ConnectedServer(config=config, client=None, error=str(exc))
            logger.warning("MCP '%s' failed: %s", config.name, exc)
        self._servers[config.name] = server
        return server

    async def connect_all(self, configs: list[MCPServerConfig]) -> None:
        for config in configs:
            await self.connect(config)

    async def disconnect(self, name: str) -> None:
        server = self._servers.pop(name, None)
        if server and server.client:
            await server.client.aclose()

    def status(self) -> list[dict]:
        return [
            {
                "name": s.config.name,
                "command": s.config.command,
                "connected": s.client is not None,
                "error": s.error,
                "tools": [t.name for t in s.tools],
            }
            for s in self._servers.values()
        ]

    def tool_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for server in self._servers.values():
            if server.client is None:
                continue
            for tool in server.tools:
                specs.append(self._wrap(server.client, server.config.name, tool))
        return specs

    def _wrap(self, client: MCPClient, server_name: str, tool: MCPTool) -> ToolSpec:
        async def handler(args: dict, ctx: ToolContext) -> str:
            return await client.call_tool(tool.name, args)

        return ToolSpec(
            name=_sanitize(f"{server_name}_{tool.name}"),
            description=f"[{server_name}] {tool.description}",
            parameters=tool.input_schema or {"type": "object", "properties": {}},
            requires_approval=self._require_approval,
            handler=handler,
        )

    async def aclose(self) -> None:
        for name in list(self._servers):
            await self.disconnect(name)

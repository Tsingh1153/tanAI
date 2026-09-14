"""Tests for the Python plugin loader and the MCP client/manager."""

from __future__ import annotations

import asyncio
from pathlib import Path

from app.agent import MCPManager, MCPServerConfig, load_plugins
from app.agent.tools import ToolContext, ToolRegistry

_BACKEND = Path(__file__).resolve().parent.parent


def _ctx() -> ToolContext:
    return ToolContext(workspace=Path("/tmp"), timeout=5, output_limit=2000)


def test_plugin_loading_and_execution() -> None:
    registry = ToolRegistry(_ctx())
    result = load_plugins(registry, str(_BACKEND / "plugins"))
    assert "example_tools" in result.loaded, result.errors
    names = {t.name for t in registry.specs()}
    assert {"word_count", "roll_dice"} <= names

    async def run() -> None:
        out = await registry.run("word_count", {"text": "one two three"})
        assert "3 words" in out

    asyncio.run(run())
    print("PLUGINS OK")


def test_mcp_client_and_manager() -> None:
    script = str(Path(__file__).resolve().parent / "mcp_mock_server.py")

    async def run() -> None:
        manager = MCPManager(require_approval=False)
        server = await manager.connect(
            MCPServerConfig(name="mock", command="python3", args=[script])
        )
        assert server.client is not None, server.error
        assert any(t.name == "echo" for t in server.tools)

        # Status reflects the connection.
        status = manager.status()[0]
        assert status["connected"] is True
        assert "echo" in status["tools"]

        # The wrapped tool actually round-trips through the server.
        specs = manager.tool_specs()
        echo = next(s for s in specs if s.name == "mock_echo")
        out = await echo.handler({"text": "hi"}, None)
        assert out == "echo: hi", out

        await manager.aclose()

    asyncio.run(run())
    print("MCP OK")


if __name__ == "__main__":
    test_plugin_loading_and_execution()
    test_mcp_client_and_manager()

"""Agent subsystem tests (no Ollama needed).

Uses a scripted provider that returns pre-programmed tool calls / answers to
exercise the loop deterministically:
1. Direct AgentService: read-only tool, approved write, denied write.
2. WebSocket path: live events + the approval round-trip.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

_WS = tempfile.mkdtemp(prefix="localmind_agent_")
os.environ.setdefault("LOCALMIND_AGENT_WORKSPACE_DIR", _WS)
os.environ.setdefault(
    "LOCALMIND_DATABASE_URL",
    f"sqlite+aiosqlite:///{tempfile.gettempdir()}/localmind_agent_test.db",
)

from fastapi.testclient import TestClient  # noqa: E402

from app.agent import AgentService, build_default_tools  # noqa: E402
from app.agent.tools import ToolContext  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.providers import build_default_registry  # noqa: E402
from app.providers.base import (  # noqa: E402
    ChatMessage,
    ChatResult,
    LLMProvider,
    ProviderModel,
    ToolCall,
)
from app.rag.embeddings import EmbeddingProvider  # noqa: E402


class ScriptedProvider(LLMProvider):
    """Returns queued ChatResults from chat(); one per step."""

    name = "ollama"

    def __init__(self, script: list[ChatResult]) -> None:
        self._script = list(script)

    async def list_models(self) -> list[ProviderModel]:
        return [ProviderModel(name="fake")]

    async def stream_chat(self, model, messages) -> AsyncIterator[str]:
        yield "unused"

    async def chat(self, model, messages, tools=None) -> ChatResult:
        return self._script.pop(0) if self._script else ChatResult("done", [])

    async def health(self) -> bool:
        return True


class FakeEmbeddings(EmbeddingProvider):
    name = "fake"
    model = "hash"

    async def embed(self, texts):
        return [[0.0] * 4 for _ in texts]

    async def health(self):
        return True


def _tools():
    ctx = ToolContext(workspace=Path(_WS), timeout=10, output_limit=4000)
    return build_default_tools(ctx)


def test_agent_loop_direct() -> None:
    async def run() -> None:
        events: list[dict] = []

        async def emit(ev):
            events.append(ev)

        # 1) Read-only tool, no approval needed.
        provider = ScriptedProvider(
            [
                ChatResult("", [ToolCall("1", "get_current_time", {})]),
                ChatResult("The time was retrieved.", []),
            ]
        )
        agent = AgentService(provider, "m", _tools(), max_steps=4)
        final = await agent.run(
            [ChatMessage("user", "what time is it")],
            emit,
            lambda t, a: _true(),
        )
        assert final == "The time was retrieved."
        assert any(e["type"] == "tool_call" for e in events)
        assert any(e["type"] == "tool_result" for e in events)

        # 2) Write requires approval — approved -> file created.
        provider = ScriptedProvider(
            [
                ChatResult(
                    "",
                    [ToolCall("1", "write_file", {"path": "note.txt", "content": "hi"})],
                ),
                ChatResult("Saved.", []),
            ]
        )
        agent = AgentService(provider, "m", _tools(), max_steps=4)
        final = await agent.run(
            [ChatMessage("user", "save a note")], emit, lambda t, a: _true()
        )
        assert final == "Saved."
        assert (Path(_WS) / "note.txt").read_text() == "hi"

        # 3) Write requires approval — denied -> file not created.
        provider = ScriptedProvider(
            [
                ChatResult(
                    "",
                    [ToolCall("1", "write_file", {"path": "secret.txt", "content": "x"})],
                ),
                ChatResult("Understood, skipped.", []),
            ]
        )
        agent = AgentService(provider, "m", _tools(), max_steps=4)
        final = await agent.run(
            [ChatMessage("user", "write secret")], emit, lambda t, a: _false()
        )
        assert final == "Understood, skipped."
        assert not (Path(_WS) / "secret.txt").exists()

    asyncio.run(run())
    print("AGENT LOOP OK")


async def _true() -> bool:
    return True


async def _false() -> bool:
    return False


def test_agent_websocket_with_approval() -> None:
    with TestClient(app) as client:
        registry = build_default_registry(get_settings())
        registry._providers["ollama"] = ScriptedProvider(
            [
                ChatResult(
                    "",
                    [ToolCall("1", "write_file", {"path": "ws.txt", "content": "yo"})],
                ),
                ChatResult("Done via websocket.", []),
            ]
        )
        app.state.registry = registry
        app.state.embeddings = FakeEmbeddings()

        conv = client.post("/api/conversations", json={}).json()
        final_text = ""
        with client.websocket_connect(f"/ws/chat/{conv['id']}") as ws:
            ws.send_json({"content": "make a file", "agent": True, "use_memory": False})
            while True:
                ev = ws.receive_json()
                if ev["type"] == "approval_request":
                    assert ev["tool"] == "write_file"
                    ws.send_text('{"approved": true}')
                elif ev["type"] == "token":
                    final_text += ev["data"]
                elif ev["type"] == "done":
                    break
                elif ev["type"] == "error":
                    raise AssertionError(ev["detail"])
        assert final_text == "Done via websocket."
        assert (Path(_WS) / "ws.txt").read_text() == "yo"

    print("AGENT WS OK")


if __name__ == "__main__":
    test_agent_loop_direct()
    test_agent_websocket_with_approval()

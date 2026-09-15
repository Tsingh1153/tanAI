"""Persona API + injection tests. Runs without Ollama using fake providers."""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "LOCALMIND_DATABASE_URL",
    f"sqlite+aiosqlite:///{tempfile.gettempdir()}/localmind_persona_test.db",
)

from collections.abc import AsyncIterator  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.providers import build_default_registry  # noqa: E402
from app.providers.base import ChatMessage, LLMProvider, ProviderModel  # noqa: E402


class SystemProbeProvider(LLMProvider):
    """Yields the concatenated system-message text so tests can inspect the prompt."""

    name = "ollama"

    async def list_models(self) -> list[ProviderModel]:
        return [ProviderModel(name="fake-model")]

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        system = " || ".join(m.content for m in messages if m.role == "system")
        yield system or "NO_SYSTEM"

    async def health(self) -> bool:
        return True


def _install() -> None:
    registry = build_default_registry(get_settings())
    registry._providers["ollama"] = SystemProbeProvider()
    app.state.registry = registry


def test_personas_listed() -> None:
    with TestClient(app) as client:
        _install()
        personas = client.get("/api/personas").json()
        ids = {p["id"] for p in personas}
        assert {
            "personal-finance",
            "markets-investing",
            "corporate-finance",
            "finance-tutor",
        } <= ids
        assert all(p["label"] and p["description"] for p in personas)


def test_persona_prompt_injected() -> None:
    with TestClient(app) as client:
        _install()
        conv = client.post("/api/conversations", json={}).json()

        # With a persona, its system prompt must reach the provider.
        with client.websocket_connect(f"/ws/chat/{conv['id']}") as ws:
            ws.send_json({"content": "Explain a DCF", "persona": "corporate-finance"})
            out = _collect(ws)
        assert "Corporate Finance" in out

        # Without a persona, that prompt must be absent.
        with client.websocket_connect(f"/ws/chat/{conv['id']}") as ws:
            ws.send_json({"content": "hello"})
            out = _collect(ws)
        assert "Corporate Finance" not in out


def _collect(ws) -> str:
    tokens: list[str] = []
    while True:
        ev = ws.receive_json()
        if ev["type"] == "token":
            tokens.append(ev["data"])
        elif ev["type"] == "done":
            break
        elif ev["type"] == "error":
            raise AssertionError(ev["detail"])
    return "".join(tokens)


if __name__ == "__main__":
    test_personas_listed()
    test_persona_prompt_injected()

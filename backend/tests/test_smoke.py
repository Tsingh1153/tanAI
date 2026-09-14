"""Smoke tests for the LocalMind backend.

These exercise the full HTTP + WebSocket request path with an in-memory database
and a fake provider, so they run anywhere without Ollama installed. They verify
conversation CRUD, model listing, and end-to-end streaming.
"""

from __future__ import annotations

import os

# Use an isolated temp DB for tests before app imports. Honors an externally
# provided URL (CI may point this at a tmpfs); defaults to the system temp dir.
import tempfile  # noqa: E402

os.environ.setdefault(
    "LOCALMIND_DATABASE_URL",
    f"sqlite+aiosqlite:///{tempfile.gettempdir()}/localmind_test.db",
)

from collections.abc import AsyncIterator  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.providers import build_default_registry  # noqa: E402
from app.providers.base import ChatMessage, LLMProvider, ProviderModel  # noqa: E402


class FakeProvider(LLMProvider):
    """Deterministic provider that echoes a canned streamed reply."""

    name = "ollama"  # masquerade as default so routes resolve it

    async def list_models(self) -> list[ProviderModel]:
        return [ProviderModel(name="fake-model", size=123, modified_at="now")]

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        for token in ["Hello", ", ", "world", "!"]:
            yield token

    async def health(self) -> bool:
        return True


def _install_fake_registry() -> None:
    registry = build_default_registry(get_settings())
    registry._providers["ollama"] = FakeProvider()  # swap in fake
    app.state.registry = registry


def test_full_flow() -> None:
    with TestClient(app) as client:
        _install_fake_registry()  # override after lifespan built the real one

        # Health
        health = client.get("/api/health").json()
        assert health["status"] == "ok"
        assert health["provider_online"] is True

        # Models
        models = client.get("/api/models").json()
        assert models[0]["name"] == "fake-model"

        # Create conversation
        conv = client.post("/api/conversations", json={}).json()
        conv_id = conv["id"]
        assert conv["title"] == "New chat"

        # Stream a turn over WebSocket
        tokens: list[str] = []
        done = False
        with client.websocket_connect(f"/ws/chat/{conv_id}") as ws:
            ws.send_json({"content": "Hi there"})
            while True:
                event = ws.receive_json()
                if event["type"] == "token":
                    tokens.append(event["data"])
                elif event["type"] == "done":
                    done = True
                    break
                elif event["type"] == "error":
                    raise AssertionError(event["detail"])
        assert done
        assert "".join(tokens) == "Hello, world!"

        # History persisted: user + assistant, and auto-title applied
        full = client.get(f"/api/conversations/{conv_id}").json()
        assert [m["role"] for m in full["messages"]] == ["user", "assistant"]
        assert full["messages"][1]["content"] == "Hello, world!"
        assert full["title"] == "Hi there"

        # Delete
        assert client.delete(f"/api/conversations/{conv_id}").status_code == 204
        assert client.get(f"/api/conversations/{conv_id}").status_code == 404

    print("SMOKE OK")


if __name__ == "__main__":
    test_full_flow()

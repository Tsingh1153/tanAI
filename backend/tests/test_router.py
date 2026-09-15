"""Auto router tests: pure classification/selection + WS integration."""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "LOCALMIND_DATABASE_URL",
    f"sqlite+aiosqlite:///{tempfile.gettempdir()}/localmind_router_test.db",
)

from collections.abc import AsyncIterator  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402
from app.providers import build_default_registry  # noqa: E402
from app.providers.base import ChatMessage, LLMProvider, ProviderModel  # noqa: E402
from app.router import choose_model, classify, route  # noqa: E402

_INSTALLED = [
    ("qwen2.5-coder:7b", "ollama"),
    ("llama3.1:8b", "ollama"),
    ("moondream:latest", "ollama"),
    ("qwen2.5:7b", "ollama"),
]


def test_classify_categories() -> None:
    assert classify("fix the bug in this python function", False, 10) == "code"
    assert classify("solve the integral of x^2", False, 10) == "math"
    assert classify("what should I have for dinner", True, 10) == "vision"
    assert classify("summarize this", False, 10_000) == "long_context"
    assert classify("hello there", False, 10) == "general"


def test_choose_prefers_specialist() -> None:
    assert choose_model("code", _INSTALLED, "qwen2.5:7b").model == "qwen2.5-coder:7b"
    assert choose_model("vision", _INSTALLED, "qwen2.5:7b").model == "moondream:latest"
    # General with no specialist match falls back to the default model.
    assert choose_model("general", _INSTALLED, "qwen2.5:7b").model == "qwen2.5:7b"


def test_choose_handles_empty() -> None:
    assert choose_model("code", [], "qwen2.5:7b") is None
    # A category with no matching model falls back to default, then first available.
    r = route("hello", False, 5, [("mistral:7b", "ollama")], "qwen2.5:7b")
    assert r.model == "mistral:7b"


class MultiModelProvider(LLMProvider):
    """Fake Ollama exposing several models; echoes the model it was asked to run."""

    name = "ollama"

    async def list_models(self) -> list[ProviderModel]:
        return [ProviderModel(name=n) for n, _ in _INSTALLED]

    async def stream_chat(
        self, model: str, messages: list[ChatMessage]
    ) -> AsyncIterator[str]:
        yield f"ran:{model}"

    async def health(self) -> bool:
        return True


def _install() -> None:
    registry = build_default_registry(get_settings())
    registry._providers["ollama"] = MultiModelProvider()
    app.state.registry = registry


def test_auto_routes_over_websocket() -> None:
    with TestClient(app) as client:
        _install()
        conv = client.post("/api/conversations", json={}).json()
        with client.websocket_connect(f"/ws/chat/{conv['id']}") as ws:
            ws.send_json({"content": "debug this python traceback", "model": "auto"})
            routed = None
            tokens: list[str] = []
            while True:
                ev = ws.receive_json()
                if ev["type"] == "router":
                    routed = ev
                elif ev["type"] == "token":
                    tokens.append(ev["data"])
                elif ev["type"] == "done":
                    break
                elif ev["type"] == "error":
                    raise AssertionError(ev["detail"])
        assert routed is not None
        assert routed["category"] == "code"
        assert routed["model"] == "qwen2.5-coder:7b"
        # The turn actually ran on the routed model.
        assert "".join(tokens) == "ran:qwen2.5-coder:7b"


if __name__ == "__main__":
    test_classify_categories()
    test_choose_prefers_specialist()
    test_auto_routes_over_websocket()

"""Computer-use gating and safety tests.

Verifies the feature is opt-in, every desktop action requires approval, and that
tools degrade gracefully when the optional OS-automation deps are absent (as in
this headless test environment).
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

from app.agent.tools import ToolContext, build_default_tools

_COMPUTER_TOOLS = {
    "screen_info",
    "screenshot",
    "move_mouse",
    "click",
    "double_click",
    "type_text",
    "press_key",
    "scroll",
}


def _ctx() -> ToolContext:
    return ToolContext(workspace=Path(tempfile.mkdtemp()), timeout=5, output_limit=2000)


def test_disabled_by_default() -> None:
    registry = build_default_tools(_ctx(), computer_use=False)
    names = {t.name for t in registry.specs()}
    assert not (_COMPUTER_TOOLS & names), "computer tools must be off by default"


def test_enabled_registers_and_requires_approval() -> None:
    registry = build_default_tools(_ctx(), computer_use=True)
    names = {t.name for t in registry.specs()}
    assert _COMPUTER_TOOLS <= names, "computer tools should be registered"
    for tool in registry.specs():
        if tool.name in _COMPUTER_TOOLS:
            assert tool.requires_approval, f"{tool.name} must require approval"


def test_graceful_without_pyautogui() -> None:
    async def run() -> None:
        registry = build_default_tools(_ctx(), computer_use=True)
        # No display / pyautogui in CI: the tool should return an error string,
        # never raise, so the agent loop keeps working.
        out = await registry.run("screenshot", {})
        assert out.startswith("Error")
        assert "unavailable" in out.lower()

    asyncio.run(run())


if __name__ == "__main__":
    test_disabled_by_default()
    test_enabled_registers_and_requires_approval()
    test_graceful_without_pyautogui()
    print("COMPUTER USE OK")

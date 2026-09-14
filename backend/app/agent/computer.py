"""Computer-use tools: control the real desktop (mouse, keyboard, screenshots).

This is the most sensitive capability in the app, so it is designed to fail
closed:

* It is only registered when ``computer_use_enabled`` is set.
* Every action is an approval-required tool (gated by the agent loop).
* The heavy OS-automation dependency (``pyautogui``) is imported lazily, so the
  core app installs and runs without it. If it is missing or there is no display
  (e.g. a headless server), each tool returns a clear error instead of crashing.

Vision note: these tools let the model *act*, but interpreting a screenshot to
decide where to click requires a vision-capable model. The screenshot tool saves
a PNG and reports its size; feeding it to a multimodal model is a follow-up.
"""

from __future__ import annotations

import os
from datetime import datetime

from .tools import ToolContext, ToolError, ToolRegistry, ToolSpec


def _pyautogui():
    """Import pyautogui lazily with a helpful error if unavailable."""

    try:
        import pyautogui  # type: ignore
    except Exception as exc:  # ImportError, or no display / no permissions
        raise ToolError(
            "Computer control is unavailable. Install the optional dependencies "
            "(pip install -r requirements-computer.txt) and, on macOS, grant "
            "Accessibility + Screen Recording permission to your terminal. "
            f"(details: {exc})"
        ) from exc
    # Safety: slamming the mouse into a screen corner aborts automation.
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    return pyautogui


async def _screen_info(args: dict, ctx: ToolContext) -> str:
    pg = _pyautogui()
    width, height = pg.size()
    x, y = pg.position()
    return f"Screen size: {width}x{height}. Cursor at ({x}, {y})."


async def _screenshot(args: dict, ctx: ToolContext) -> str:
    pg = _pyautogui()
    shots = ctx.workspace / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    name = f"shot_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.png"
    path = shots / name
    image = pg.screenshot()
    image.save(str(path))
    rel = os.path.relpath(path, ctx.workspace)
    return (
        f"Screenshot saved to {rel} ({image.width}x{image.height}). "
        "Attach a vision-capable model to interpret its contents."
    )


async def _move_mouse(args: dict, ctx: ToolContext) -> str:
    pg = _pyautogui()
    x, y = int(args.get("x", 0)), int(args.get("y", 0))
    pg.moveTo(x, y, duration=0.2)
    return f"Moved cursor to ({x}, {y})."


async def _click(args: dict, ctx: ToolContext) -> str:
    pg = _pyautogui()
    button = args.get("button", "left")
    if button not in {"left", "right", "middle"}:
        raise ToolError("button must be left, right, or middle.")
    if "x" in args and "y" in args:
        pg.click(int(args["x"]), int(args["y"]), button=button)
        return f"{button}-clicked at ({args['x']}, {args['y']})."
    pg.click(button=button)
    return f"{button}-clicked at current position."


async def _double_click(args: dict, ctx: ToolContext) -> str:
    pg = _pyautogui()
    if "x" in args and "y" in args:
        pg.doubleClick(int(args["x"]), int(args["y"]))
        return f"Double-clicked at ({args['x']}, {args['y']})."
    pg.doubleClick()
    return "Double-clicked at current position."


async def _type_text(args: dict, ctx: ToolContext) -> str:
    pg = _pyautogui()
    text = args.get("text", "")
    if not text:
        raise ToolError("Missing 'text'.")
    pg.typewrite(text, interval=0.01)
    return f"Typed {len(text)} characters."


async def _press_key(args: dict, ctx: ToolContext) -> str:
    pg = _pyautogui()
    keys = args.get("keys", "")
    if not keys:
        raise ToolError("Missing 'keys' (e.g. 'enter' or 'command,c').")
    combo = [k.strip() for k in keys.split(",") if k.strip()]
    if len(combo) > 1:
        pg.hotkey(*combo)
        return f"Pressed hotkey {'+'.join(combo)}."
    pg.press(combo[0])
    return f"Pressed {combo[0]}."


async def _scroll(args: dict, ctx: ToolContext) -> str:
    pg = _pyautogui()
    amount = int(args.get("amount", 0))
    pg.scroll(amount)
    return f"Scrolled {amount}."


def register_computer_tools(registry: ToolRegistry) -> None:
    """Add the approval-gated desktop-control tools to a registry."""

    obj = {"type": "object", "properties": {}}
    xy = {
        "type": "object",
        "properties": {
            "x": {"type": "integer"},
            "y": {"type": "integer"},
        },
    }

    registry.register(
        ToolSpec(
            name="screen_info",
            description="Get the screen resolution and current cursor position.",
            parameters=obj,
            requires_approval=True,
            handler=_screen_info,
        )
    )
    registry.register(
        ToolSpec(
            name="screenshot",
            description="Capture the current screen to a PNG in the workspace.",
            parameters=obj,
            requires_approval=True,
            handler=_screenshot,
        )
    )
    registry.register(
        ToolSpec(
            name="move_mouse",
            description="Move the mouse cursor to absolute screen coordinates.",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
            requires_approval=True,
            handler=_move_mouse,
        )
    )
    registry.register(
        ToolSpec(
            name="click",
            description="Click the mouse, optionally at coordinates (left/right/middle).",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {"type": "string", "enum": ["left", "right", "middle"]},
                },
            },
            requires_approval=True,
            handler=_click,
        )
    )
    registry.register(
        ToolSpec(
            name="double_click",
            description="Double-click, optionally at coordinates.",
            parameters=xy,
            requires_approval=True,
            handler=_double_click,
        )
    )
    registry.register(
        ToolSpec(
            name="type_text",
            description="Type text at the current keyboard focus.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            requires_approval=True,
            handler=_type_text,
        )
    )
    registry.register(
        ToolSpec(
            name="press_key",
            description=(
                "Press a key or hotkey. Use a comma for combos, e.g. "
                "'enter' or 'command,c'."
            ),
            parameters={
                "type": "object",
                "properties": {"keys": {"type": "string"}},
                "required": ["keys"],
            },
            requires_approval=True,
            handler=_press_key,
        )
    )
    registry.register(
        ToolSpec(
            name="scroll",
            description="Scroll vertically by an amount (positive up, negative down).",
            parameters={
                "type": "object",
                "properties": {"amount": {"type": "integer"}},
                "required": ["amount"],
            },
            requires_approval=True,
            handler=_scroll,
        )
    )

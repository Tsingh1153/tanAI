"""Tool registry and built-in tools. Writing/executing tools are approval-gated
and confined to a sandbox root; all invocations are logged."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("localmind.agent.tools")


class ToolError(Exception):
    """Raised when a tool cannot complete; surfaced to the model as an error."""


@dataclass(slots=True)
class ToolContext:
    workspace: Path
    timeout: float
    output_limit: int


ToolHandler = Callable[[dict, ToolContext], Awaitable[str]]


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict
    requires_approval: bool
    handler: ToolHandler

    def schema(self) -> dict:
        """Provider-facing tool schema (OpenAI/Ollama function format)."""

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    def __init__(self, context: ToolContext) -> None:
        self._context = context
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def specs(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def schemas(self) -> list[dict]:
        return [t.schema() for t in self._tools.values()]

    async def run(self, name: str, arguments: dict) -> str:
        spec = self._tools.get(name)
        if spec is None:
            return f"Error: unknown tool '{name}'."
        try:
            result = await spec.handler(arguments, self._context)
            logger.info("tool ok name=%s args=%s", name, _short(arguments))
            return _truncate(result, self._context.output_limit)
        except ToolError as exc:
            logger.warning("tool error name=%s detail=%s", name, exc)
            return f"Error: {exc}"
        except Exception as exc:  # never let a tool crash the agent loop
            logger.exception("tool crash name=%s", name)
            return f"Error: {type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _short(value: object, limit: int = 200) -> str:
    text = str(value)
    return text if len(text) <= limit else text[:limit] + "…"


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…[truncated, {len(text) - limit} more chars]"


def _resolve_in_workspace(workspace: Path, rel: str) -> Path:
    """Resolve a user-supplied path and ensure it stays inside the sandbox."""

    candidate = (workspace / rel).resolve()
    root = workspace.resolve()
    if candidate != root and root not in candidate.parents:
        raise ToolError(f"Path '{rel}' escapes the agent workspace and is not allowed.")
    return candidate


def _is_public_url(url: str) -> bool:
    """Block non-HTTP schemes and requests to private/loopback addresses."""

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    try:
        addrinfo = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror:
        return False
    for info in addrinfo:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
    return True


# --------------------------------------------------------------------------- #
# Tool implementations
# --------------------------------------------------------------------------- #
async def _tool_time(args: dict, ctx: ToolContext) -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).astimezone().isoformat()


async def _tool_web_fetch(args: dict, ctx: ToolContext) -> str:
    from bs4 import BeautifulSoup

    url = (args.get("url") or "").strip()
    if not url:
        raise ToolError("Missing 'url'.")
    if not _is_public_url(url):
        raise ToolError("URL is not a public http(s) address (blocked).")
    try:
        async with httpx.AsyncClient(
            timeout=20, follow_redirects=True, trust_env=False
        ) as client:
            resp = await client.get(url, headers={"User-Agent": "tanAI/1.0"})
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise ToolError(f"Fetch failed: {exc}") from exc

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = "\n".join(
        line.strip() for line in soup.get_text("\n").splitlines() if line.strip()
    )
    return f"Fetched {url}:\n\n{text}"


async def _tool_fs_list(args: dict, ctx: ToolContext) -> str:
    target = _resolve_in_workspace(ctx.workspace, args.get("path", "."))
    if not target.exists():
        raise ToolError("Path does not exist.")
    if not target.is_dir():
        raise ToolError("Path is not a directory.")
    entries = sorted(f"{p.name}/" if p.is_dir() else p.name for p in target.iterdir())
    listing = "\n".join(entries) if entries else "(empty)"
    return f"Contents of {args.get('path', '.')}:\n{listing}"


async def _tool_fs_read(args: dict, ctx: ToolContext) -> str:
    target = _resolve_in_workspace(ctx.workspace, args.get("path", ""))
    if not target.exists() or not target.is_file():
        raise ToolError("File does not exist.")
    return target.read_text(encoding="utf-8", errors="replace")


async def _tool_fs_write(args: dict, ctx: ToolContext) -> str:
    rel = args.get("path", "")
    content = args.get("content", "")
    if not rel:
        raise ToolError("Missing 'path'.")
    target = _resolve_in_workspace(ctx.workspace, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} characters to {rel}."


async def _tool_python(args: dict, ctx: ToolContext) -> str:
    code = args.get("code", "")
    if not code.strip():
        raise ToolError("Missing 'code'.")
    proc = await asyncio.create_subprocess_exec(
        "python3",
        "-c",
        code,
        cwd=str(ctx.workspace),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=ctx.timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise ToolError(f"Execution timed out after {ctx.timeout:.0f}s.")
    output = stdout.decode("utf-8", errors="replace").strip()
    return output or "(no output)"


def build_default_tools(
    context: ToolContext, computer_use: bool = False
) -> ToolRegistry:
    registry = ToolRegistry(context)

    registry.register(
        ToolSpec(
            name="get_current_time",
            description="Get the current local date and time (ISO 8601).",
            parameters={"type": "object", "properties": {}},
            requires_approval=False,
            handler=_tool_time,
        )
    )
    registry.register(
        ToolSpec(
            name="web_fetch",
            description=(
                "Fetch a public web page by URL and return its readable text. "
                "Use for looking up documentation or current information."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "http(s) URL to fetch"}
                },
                "required": ["url"],
            },
            requires_approval=False,
            handler=_tool_web_fetch,
        )
    )
    registry.register(
        ToolSpec(
            name="list_files",
            description="List files and folders at a path (absolute or relative).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path (absolute or relative to root)",
                        "default": ".",
                    }
                },
            },
            requires_approval=False,
            handler=_tool_fs_list,
        )
    )
    registry.register(
        ToolSpec(
            name="read_file",
            description="Read a text file (path may be absolute or relative to root).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path (absolute or relative to root)",
                    }
                },
                "required": ["path"],
            },
            requires_approval=False,
            handler=_tool_fs_read,
        )
    )
    registry.register(
        ToolSpec(
            name="write_file",
            description="Create or overwrite a text file (absolute or relative path).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "File path (absolute or relative to root)",
                    },
                    "content": {"type": "string", "description": "File contents"},
                },
                "required": ["path", "content"],
            },
            requires_approval=True,
            handler=_tool_fs_write,
        )
    )
    registry.register(
        ToolSpec(
            name="run_python",
            description=(
                "Execute a short Python 3 script in the sandboxed workspace and "
                "return its stdout. Use for calculations, data processing, or "
                "generating files."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "Python source code"}
                },
                "required": ["code"],
            },
            requires_approval=True,
            handler=_tool_python,
        )
    )

    # Desktop-control tools are opt-in and always approval-gated.
    if computer_use:
        from .computer import register_computer_tools

        register_computer_tools(registry)

    return registry

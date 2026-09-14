"""Minimal MCP stdio client (line-delimited JSON-RPC 2.0).

Implements only initialize / tools/list / tools/call to avoid the MCP SDK,
whose transitive deps clash with our pinned FastAPI/Starlette. A background
reader dispatches responses to pending requests by id.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass

_PROTOCOL_VERSION = "2024-11-05"


class MCPError(RuntimeError):
    """Raised when an MCP server returns an error or misbehaves."""


@dataclass(slots=True)
class MCPTool:
    name: str
    description: str
    input_schema: dict


class MCPClient:
    def __init__(self) -> None:
        self._proc: asyncio.subprocess.Process | None = None
        self._pending: dict[int, asyncio.Future] = {}
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None
        self._next_id = 0

    async def connect(
        self,
        command: str,
        args: list[str],
        env: dict[str, str] | None = None,
        timeout: float = 20.0,
    ) -> None:
        merged_env = {**os.environ, **(env or {})}
        self._proc = await asyncio.create_subprocess_exec(
            command,
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )
        self._reader_task = asyncio.create_task(self._read_loop())
        self._stderr_task = asyncio.create_task(self._drain_stderr())

        await self._request(
            "initialize",
            {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "tanAI", "version": "0.1.0"},
            },
            timeout,
        )
        await self._notify("notifications/initialized")

    async def list_tools(self, timeout: float = 20.0) -> list[MCPTool]:
        result = await self._request("tools/list", {}, timeout)
        tools: list[MCPTool] = []
        for item in result.get("tools", []):
            tools.append(
                MCPTool(
                    name=item.get("name", ""),
                    description=item.get("description", "") or "",
                    input_schema=item.get("inputSchema") or {"type": "object"},
                )
            )
        return tools

    async def call_tool(self, name: str, arguments: dict, timeout: float = 60.0) -> str:
        result = await self._request(
            "tools/call", {"name": name, "arguments": arguments}, timeout
        )
        # Flatten the content blocks into text for the model.
        parts: list[str] = []
        for block in result.get("content", []):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            else:
                parts.append(json.dumps(block))
        text = "\n".join(p for p in parts if p) or "(no output)"
        if result.get("isError"):
            return f"Error from tool: {text}"
        return text

    async def aclose(self) -> None:
        for task in (self._reader_task, self._stderr_task):
            if task:
                task.cancel()
        if self._proc and self._proc.returncode is None:
            try:
                self._proc.terminate()
                await asyncio.wait_for(self._proc.wait(), timeout=5)
            except (ProcessLookupError, asyncio.TimeoutError):
                try:
                    self._proc.kill()
                except ProcessLookupError:
                    pass

    # ---- internals ---- #
    async def _request(self, method: str, params: dict, timeout: float) -> dict:
        if self._proc is None or self._proc.stdin is None:
            raise MCPError("MCP server is not connected.")
        self._next_id += 1
        request_id = self._next_id
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future

        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        }
        self._proc.stdin.write((json.dumps(message) + "\n").encode())
        await self._proc.stdin.drain()

        try:
            response = await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError as exc:
            self._pending.pop(request_id, None)
            raise MCPError(f"MCP '{method}' timed out.") from exc

        if "error" in response:
            raise MCPError(str(response["error"]))
        return response.get("result", {})

    async def _notify(self, method: str, params: dict | None = None) -> None:
        if self._proc is None or self._proc.stdin is None:
            return
        message = {"jsonrpc": "2.0", "method": method, "params": params or {}}
        self._proc.stdin.write((json.dumps(message) + "\n").encode())
        await self._proc.stdin.drain()

    async def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        while True:
            line = await self._proc.stdout.readline()
            if not line:
                break  # server closed
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            msg_id = message.get("id")
            if msg_id is not None and msg_id in self._pending:
                future = self._pending.pop(msg_id)
                if not future.done():
                    future.set_result(message)

    async def _drain_stderr(self) -> None:
        assert self._proc and self._proc.stderr
        while True:
            line = await self._proc.stderr.readline()
            if not line:
                break

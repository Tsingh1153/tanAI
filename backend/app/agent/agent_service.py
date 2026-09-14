"""Agent orchestration: the plan-execute tool loop, gated by an approval callback."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ..providers import ChatMessage, LLMProvider
from .tools import ToolRegistry

# An event dict pushed to the UI, e.g. {"type": "tool_call", ...}.
AgentEvent = dict

EmitFn = Callable[[AgentEvent], Awaitable[None]]
ApprovalFn = Callable[[str, dict], Awaitable[bool]]

_SYSTEM_PROMPT = (
    "You are a capable assistant with access to tools. Use them when they help "
    "you answer accurately or complete a task — for example, run Python for "
    "calculations, read or write files in your workspace, or fetch a web page "
    "for current information. Think step by step, call one or more tools as "
    "needed, then give a clear final answer. Do not claim to have done something "
    "you did not do with a tool."
)


class AgentService:
    def __init__(
        self,
        provider: LLMProvider,
        model: str,
        tools: ToolRegistry,
        max_steps: int,
    ) -> None:
        self._provider = provider
        self._model = model
        self._tools = tools
        self._max_steps = max_steps

    async def run(
        self,
        history: list[ChatMessage],
        emit: EmitFn,
        request_approval: ApprovalFn,
        extra_system: list[str] | None = None,
    ) -> str:
        """Execute the agent loop and return the final assistant text."""

        messages: list[ChatMessage] = [
            ChatMessage(role="system", content=_SYSTEM_PROMPT)
        ]
        for prime in extra_system or []:
            if prime:
                messages.append(ChatMessage(role="system", content=prime))
        messages.extend(history)

        schemas = self._tools.schemas()

        for _ in range(self._max_steps):
            result = await self._provider.chat(self._model, messages, schemas)

            if not result.tool_calls:
                return result.content or "(no response)"

            messages.append(
                ChatMessage(
                    role="assistant",
                    content=result.content or "",
                    tool_calls=result.tool_calls,
                )
            )

            for call in result.tool_calls:
                spec = self._tools.get(call.name)
                needs_approval = bool(spec and spec.requires_approval)
                await emit(
                    {
                        "type": "tool_call",
                        "tool": call.name,
                        "arguments": call.arguments,
                        "requires_approval": needs_approval,
                    }
                )

                if needs_approval:
                    approved = await request_approval(call.name, call.arguments)
                    if not approved:
                        output = "The user denied this action."
                        await emit(
                            {
                                "type": "tool_result",
                                "tool": call.name,
                                "output": output,
                                "denied": True,
                            }
                        )
                        messages.append(
                            ChatMessage(
                                role="tool",
                                content=output,
                                tool_name=call.name,
                                tool_call_id=call.id,
                            )
                        )
                        continue

                output = await self._tools.run(call.name, call.arguments)
                await emit({"type": "tool_result", "tool": call.name, "output": output})
                messages.append(
                    ChatMessage(
                        role="tool",
                        content=output,
                        tool_name=call.name,
                        tool_call_id=call.id,
                    )
                )

        # Step budget exhausted: force a final answer without tools.
        final = await self._provider.chat(self._model, messages, None)
        return final.content or "I reached my step limit before finishing."

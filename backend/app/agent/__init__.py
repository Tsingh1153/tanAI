"""Autonomous agent subsystem.

A plan-execute loop lets the model call tools to gather information and take
actions, observing each result before deciding the next step. Safety is central:
filesystem access and code execution are confined to a sandbox workspace, and any
tool that writes or executes requires explicit user approval. Every tool call is
audit-logged.
"""

from .agent_service import AgentEvent, AgentService
from .mcp_manager import MCPManager, MCPServerConfig
from .plugins import load_plugins
from .tools import ToolRegistry, build_default_tools

__all__ = [
    "AgentEvent",
    "AgentService",
    "MCPManager",
    "MCPServerConfig",
    "ToolRegistry",
    "build_default_tools",
    "load_plugins",
]

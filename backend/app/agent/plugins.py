"""Python plugin loader.

A plugin is any ``.py`` file in the plugins directory that defines a top-level
``register(registry)`` function. It receives the live :class:`ToolRegistry` and
can add one or more tools via ``registry.register(ToolSpec(...))``. Plugins are
loaded fresh each time tools are built, so dropping in a new file takes effect on
the next agent turn (simple hot-loading) without a restart.

Plugins execute in-process with full trust — they are ordinary Python. Only add
plugins you trust; per-tool ``requires_approval`` still gates sensitive actions.
"""

from __future__ import annotations

import importlib.util
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .tools import ToolRegistry

logger = logging.getLogger("localmind.agent.plugins")


@dataclass(slots=True)
class PluginLoadResult:
    loaded: list[str] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


def load_plugins(registry: ToolRegistry, plugins_dir: str) -> PluginLoadResult:
    """Import every plugin file and let it register tools. Never raises."""

    result = PluginLoadResult()
    root = Path(plugins_dir)
    if not root.is_dir():
        return result

    for path in sorted(root.glob("*.py")):
        if path.name.startswith("_"):
            continue  # skip private/helper modules
        module_name = f"localmind_plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise ImportError("could not create module spec")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            register = getattr(module, "register", None)
            if not callable(register):
                raise AttributeError("plugin has no register(registry) function")
            register(registry)
            result.loaded.append(path.stem)
        except Exception as exc:  # a bad plugin must not break the app
            logger.warning("plugin %s failed to load: %s", path.name, exc)
            result.errors[path.stem] = str(exc)

    return result

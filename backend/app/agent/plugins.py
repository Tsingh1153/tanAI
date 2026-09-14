"""Python plugin loader: import each .py in the plugins dir and call its
register(registry). Loaded fresh per tool build, so new files hot-load. Plugins
run in-process with full trust — only add ones you trust."""

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

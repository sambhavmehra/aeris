"""
AERIS — Plugin System: Plugin Registry
Dynamic plugin discovery, loading, and lifecycle management.
"""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("AerisPluginRegistry")

PLUGIN_DIR = Path(__file__).resolve().parent.parent.parent / "plugins"


@dataclass
class PluginMeta:
    """Metadata for a loaded plugin."""
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    enabled: bool = True
    module: Any = None
    hooks: Dict[str, Callable] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "enabled": self.enabled,
            "hooks": list(self.hooks.keys()),
        }


class PluginRegistry:
    """
    Discovers, loads, and manages plugins from the plugins/ directory.

    Plugin contract: each plugin is a Python file or package in plugins/ that
    exposes a `register(registry)` function. The plugin calls
    `registry.register_hook(hook_name, callable)` to attach behavior.
    """

    def __init__(self):
        self._plugins: Dict[str, PluginMeta] = {}
        self._hooks: Dict[str, List[Callable]] = {}
        PLUGIN_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"PluginRegistry initialized. Plugin dir: {PLUGIN_DIR}")

    def discover(self) -> List[str]:
        """Discover available plugins in the plugins directory."""
        discovered = []
        if not PLUGIN_DIR.exists():
            return discovered

        for item in PLUGIN_DIR.iterdir():
            if item.suffix == ".py" and not item.name.startswith("_"):
                discovered.append(item.stem)
            elif item.is_dir() and (item / "__init__.py").exists():
                discovered.append(item.name)
        return discovered

    def load(self, plugin_name: str) -> bool:
        """Load a single plugin by name."""
        if plugin_name in self._plugins:
            logger.warning(f"Plugin '{plugin_name}' already loaded.")
            return True

        try:
            module = importlib.import_module(f"plugins.{plugin_name}")
            meta = PluginMeta(
                name=plugin_name,
                version=getattr(module, "__version__", "1.0.0"),
                description=getattr(module, "__description__", ""),
                author=getattr(module, "__author__", ""),
                module=module,
            )

            # Call the plugin's register function if it exists
            if hasattr(module, "register"):
                module.register(self)

            self._plugins[plugin_name] = meta
            logger.info(f"Plugin loaded: {plugin_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to load plugin '{plugin_name}': {e}")
            return False

    def load_all(self) -> Dict[str, bool]:
        """Discover and load all plugins. Returns {name: success}."""
        results = {}
        for name in self.discover():
            results[name] = self.load(name)
        return results

    def unload(self, plugin_name: str) -> bool:
        """Unload a plugin."""
        if plugin_name not in self._plugins:
            return False

        plugin = self._plugins[plugin_name]
        # Remove hooks registered by this plugin
        for hook_name, callbacks in self._hooks.items():
            self._hooks[hook_name] = [
                cb for cb in callbacks
                if not getattr(cb, "_plugin_name", None) == plugin_name
            ]

        del self._plugins[plugin_name]
        logger.info(f"Plugin unloaded: {plugin_name}")
        return True

    def register_hook(self, hook_name: str, callback: Callable, plugin_name: str = ""):
        """Register a hook callback (called by plugins during registration)."""
        callback._plugin_name = plugin_name  # Tag for cleanup
        self._hooks.setdefault(hook_name, []).append(callback)

    async def trigger_hook(self, hook_name: str, **kwargs) -> List[Any]:
        """Trigger all callbacks for a hook. Returns list of results."""
        import asyncio
        results = []
        for cb in self._hooks.get(hook_name, []):
            try:
                if asyncio.iscoroutinefunction(cb):
                    result = await cb(**kwargs)
                else:
                    result = cb(**kwargs)
                results.append(result)
            except Exception as e:
                logger.warning(f"Hook '{hook_name}' callback error: {e}")
        return results

    def get_loaded_plugins(self) -> List[Dict]:
        return [p.to_dict() for p in self._plugins.values()]

    def get_plugin(self, name: str) -> Optional[PluginMeta]:
        return self._plugins.get(name)

    def get_hook_names(self) -> List[str]:
        return list(self._hooks.keys())


# ── Singleton ──────────────────────────────────────────────────────────
_plugin_registry: Optional[PluginRegistry] = None

def get_plugin_registry() -> PluginRegistry:
    global _plugin_registry
    if _plugin_registry is None:
        _plugin_registry = PluginRegistry()
    return _plugin_registry

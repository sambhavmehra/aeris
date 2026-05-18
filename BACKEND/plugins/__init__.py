"""
AERIS — Plugin System Package
Dynamic plugin discovery, loading, and hook management.
"""
from core.plugins.plugin_registry import PluginRegistry, PluginMeta, get_plugin_registry

__all__ = [
    "PluginRegistry", "PluginMeta", "get_plugin_registry",
]

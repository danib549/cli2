"""Tool registry with auto-discovery."""

import importlib
import pkgutil
from pathlib import Path
from typing import TYPE_CHECKING, Type

from opencode.tools.base import Tool

if TYPE_CHECKING:
    from opencode.mode import ModeManager
    from opencode.config import Config
    from opencode.workspace import Workspace


class ToolRegistry:
    """Registry of available tools with auto-discovery."""

    def __init__(
        self,
        mode_manager: "ModeManager" = None,
        config: "Config" = None,
        checkpoint_fn: callable = None,
        workspace: "Workspace" = None,
    ):
        self._tools: dict[str, Tool] = {}
        self._mode_manager = mode_manager
        self._config = config
        self._checkpoint_fn = checkpoint_fn
        self._workspace = workspace

    def register(self, tool_class: Type[Tool]) -> Tool:
        """Register a tool class and instantiate it.

        Args:
            tool_class: The Tool subclass to register.

        Returns:
            The instantiated tool.
        """
        tool = tool_class(
            mode_manager=self._mode_manager,
            config=self._config,
            checkpoint_fn=self._checkpoint_fn,
            workspace=self._workspace,
        )
        self._tools[tool.name] = tool
        return tool

    def register_instance(self, tool: Tool) -> None:
        """Register an already instantiated tool."""
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool:
        """Get a tool by name.

        Args:
            name: The tool name.

        Returns:
            The tool instance.

        Raises:
            KeyError: If tool not found.
        """
        if name not in self._tools:
            raise KeyError(f"Unknown tool: {name}")
        return self._tools[name]

    def has(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def all_tools(self) -> list[Tool]:
        """Get all registered tools."""
        return list(self._tools.values())

    def discover(self, package_name: str = "opencode.tools") -> int:
        """Auto-discover and register tools from a package.

        Scans all modules in the package for Tool subclasses
        and registers them automatically.

        Args:
            package_name: The package to scan for tools.

        Returns:
            Number of tools discovered.
        """
        count = 0

        try:
            package = importlib.import_module(package_name)
        except ImportError:
            return 0

        # Get package path
        if not hasattr(package, "__path__"):
            return 0

        # Iterate through all modules in the package
        for importer, modname, ispkg in pkgutil.iter_modules(package.__path__):
            if modname in ("__init__", "base", "registry"):
                continue

            try:
                module = importlib.import_module(f"{package_name}.{modname}")

                # Find all Tool subclasses in the module
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)

                    if (
                        isinstance(attr, type)
                        and issubclass(attr, Tool)
                        and attr is not Tool
                        and hasattr(attr, "name")
                        and attr.name != "base"
                    ):
                        # Don't re-register
                        if attr.name not in self._tools:
                            self.register(attr)
                            count += 1

            except Exception:
                continue

        return count

    def get_anthropic_tools(self) -> list[dict]:
        """Get all tools in Anthropic format."""
        return [tool.to_anthropic_tool() for tool in self._tools.values()]

    def get_openai_tools(self) -> list[dict]:
        """Get all tools in OpenAI format."""
        return [tool.to_openai_tool() for tool in self._tools.values()]

    def get_tool_descriptions(self) -> str:
        """Get formatted tool descriptions for system prompt."""
        lines = []
        for tool in self._tools.values():
            mode_note = " (BUILD mode only)" if tool.requires_build_mode else ""
            lines.append(f"- {tool.name}: {tool.description}{mode_note}")
        return "\n".join(lines)

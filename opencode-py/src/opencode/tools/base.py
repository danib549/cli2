"""Tool base class with LLM schema support."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from opencode.mode import ModeManager
    from opencode.config import Config
    from opencode.workspace import Workspace


@dataclass
class ToolResult:
    """Result of a tool execution.

    Attributes:
        success: Whether the tool succeeded.
        output: Output to display to user (may be truncated).
        error: Error message if failed.
        _llm_output: Full output for LLM (if different from display output).
                     If None, `output` is used for both display and LLM.
    """
    success: bool
    output: str
    error: str = ""
    _llm_output: str = None

    @property
    def llm_output(self) -> str:
        """Get output to send to LLM (full content)."""
        return self._llm_output if self._llm_output is not None else self.output

    @classmethod
    def ok(cls, output: str = "") -> "ToolResult":
        """Create a successful result."""
        return cls(success=True, output=output)

    @classmethod
    def fail(cls, error: str, output: str = "") -> "ToolResult":
        """Create a failed result."""
        return cls(success=False, output=output, error=error)


class Tool(ABC):
    """Base class for all tools.

    To create a new tool:
    1. Subclass Tool
    2. Set name and description
    3. Implement execute() and get_schema()
    4. Place in tools/ directory for auto-discovery
    """

    name: str = "base"
    description: str = "Base tool"
    requires_build_mode: bool = False

    def __init__(
        self,
        mode_manager: "ModeManager" = None,
        config: "Config" = None,
        checkpoint_fn: callable = None,
        workspace: "Workspace" = None,
    ):
        self.mode = mode_manager
        self.config = config
        self.checkpoint_fn = checkpoint_fn
        self.workspace = workspace

    def _resolve_path(self, path: str) -> Path:
        """Resolve path within workspace boundaries.

        Args:
            path: File path (relative or absolute).

        Returns:
            Resolved absolute path.

        Raises:
            ValueError: If path is outside workspace boundaries.
        """
        if self.workspace:
            from opencode.workspace import WorkspaceError
            try:
                return self.workspace.resolve_path(path)
            except WorkspaceError as e:
                raise ValueError(str(e))

        # No workspace - resolve relative to cwd
        p = Path(path)
        if not p.is_absolute():
            p = Path.cwd() / p
        return p.resolve()

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given arguments.

        Args:
            **kwargs: Tool-specific arguments.

        Returns:
            ToolResult with success status and output/error.
        """
        pass

    @abstractmethod
    def get_schema(self) -> dict:
        """Return JSON schema for LLM function calling.

        Returns:
            Dict with tool schema in OpenAI/Anthropic function format.
        """
        pass

    def _check_mode(self) -> None:
        """Check if current mode allows this tool."""
        if self.requires_build_mode and self.mode:
            self.mode.require_build(self.name)

    def _checkpoint(self, description: str) -> None:
        """Create a checkpoint before mutation."""
        if self.checkpoint_fn:
            self.checkpoint_fn(description)

    def to_anthropic_tool(self) -> dict:
        """Convert to Anthropic tool format."""
        schema = self.get_schema()
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": schema.get("properties", {}),
                "required": schema.get("required", []),
            }
        }

    def to_openai_tool(self) -> dict:
        """Convert to OpenAI function format."""
        schema = self.get_schema()
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": schema.get("properties", {}),
                    "required": schema.get("required", []),
                }
            }
        }

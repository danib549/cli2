"""Modular tool system.

Provides:
- ToolRegistry with auto-discovery
- Tool base class
- Built-in tools: read, edit, write, bash

Adding a new tool:
1. Create tools/mytool.py
2. Subclass Tool, implement execute() and get_schema()
3. Tool is auto-discovered on startup
"""

from opencode.tools.base import Tool, ToolResult
from opencode.tools.registry import ToolRegistry
from opencode.tools.read import ReadTool
from opencode.tools.edit import EditTool
from opencode.tools.write import WriteTool
from opencode.tools.bash import BashTool

__all__ = [
    "Tool",
    "ToolResult",
    "ToolRegistry",
    "ReadTool",
    "EditTool",
    "WriteTool",
    "BashTool",
]

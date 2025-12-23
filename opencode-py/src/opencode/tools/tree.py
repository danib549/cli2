"""Tree tool - display directory structure."""

from pathlib import Path
from typing import Optional

from opencode.tools.base import Tool, ToolResult


class TreeTool(Tool):
    """Display directory structure as a tree."""

    name = "tree"
    description = "Display the directory structure as a tree view"
    requires_build_mode = False

    SKIP_DIRS = {
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "dist", "build", ".tox", "target", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", "htmlcov", ".coverage",
        ".eggs", "*.egg-info",
    }

    SKIP_FILES = {
        ".DS_Store", "Thumbs.db", "*.pyc", "*.pyo", "*.so",
        "*.dll", "*.exe", "*.bin", "*.lock",
    }

    def execute(
        self,
        path: str = ".",
        depth: int = 3,
        show_hidden: bool = False,
        dirs_only: bool = False,
    ) -> ToolResult:
        """Display directory structure.

        Args:
            path: Root path to display (default: current directory).
            depth: Maximum depth to traverse (default: 3).
            show_hidden: Show hidden files/directories (default: False).
            dirs_only: Only show directories (default: False).

        Returns:
            ToolResult with tree structure.
        """
        # Resolve path
        try:
            root_path = self._resolve_path(path)
        except ValueError as e:
            return ToolResult.fail(str(e))

        if not root_path.is_dir():
            return ToolResult.fail(f"Not a directory: {path}")

        # Build tree
        lines = []
        self._build_tree(
            root_path,
            lines,
            prefix="",
            depth=depth,
            current_depth=0,
            show_hidden=show_hidden,
            dirs_only=dirs_only,
        )

        if not lines:
            return ToolResult.ok(f"{path}/ (empty)")

        # Add root
        output = f"{root_path.name}/\n" + "\n".join(lines)
        return ToolResult.ok(output)

    def _build_tree(
        self,
        dir_path: Path,
        lines: list,
        prefix: str,
        depth: int,
        current_depth: int,
        show_hidden: bool,
        dirs_only: bool,
    ) -> None:
        """Recursively build tree structure."""
        if current_depth >= depth:
            return

        try:
            entries = sorted(dir_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
        except PermissionError:
            lines.append(f"{prefix}[permission denied]")
            return

        # Filter entries
        filtered = []
        for entry in entries:
            name = entry.name

            # Skip hidden unless requested
            if not show_hidden and name.startswith('.'):
                continue

            # Skip known directories to ignore
            if entry.is_dir() and name in self.SKIP_DIRS:
                continue

            # Skip files if dirs_only
            if dirs_only and not entry.is_dir():
                continue

            # Skip known files to ignore
            if entry.is_file():
                skip = False
                for pattern in self.SKIP_FILES:
                    if pattern.startswith('*'):
                        if name.endswith(pattern[1:]):
                            skip = True
                            break
                    elif name == pattern:
                        skip = True
                        break
                if skip:
                    continue

            filtered.append(entry)

        # Build tree lines
        for i, entry in enumerate(filtered):
            is_last = (i == len(filtered) - 1)
            connector = "└── " if is_last else "├── "
            child_prefix = prefix + ("    " if is_last else "│   ")

            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                self._build_tree(
                    entry,
                    lines,
                    child_prefix,
                    depth,
                    current_depth + 1,
                    show_hidden,
                    dirs_only,
                )
            else:
                # Show file with size
                try:
                    size = entry.stat().st_size
                    size_str = self._format_size(size)
                    lines.append(f"{prefix}{connector}{entry.name} ({size_str})")
                except Exception:
                    lines.append(f"{prefix}{connector}{entry.name}")

    def _format_size(self, size: int) -> str:
        """Format file size in human-readable form."""
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f}KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f}MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f}GB"

    def get_schema(self) -> dict:
        """Return JSON schema for LLM function calling."""
        return {
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Root path to display (default: current directory)",
                    "default": "."
                },
                "depth": {
                    "type": "integer",
                    "description": "Maximum depth to traverse (default: 3)",
                    "default": 3
                },
                "show_hidden": {
                    "type": "boolean",
                    "description": "Show hidden files/directories (default: false)",
                    "default": False
                },
                "dirs_only": {
                    "type": "boolean",
                    "description": "Only show directories (default: false)",
                    "default": False
                }
            },
            "required": []
        }

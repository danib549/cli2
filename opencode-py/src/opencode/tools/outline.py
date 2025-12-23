"""Outline tool - show structure of a file (classes, functions, etc.)."""

import re
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from opencode.tools.base import Tool, ToolResult


@dataclass
class Symbol:
    """A symbol in the outline."""
    name: str
    kind: str
    line: int
    indent: int
    children: list = None

    def __post_init__(self):
        if self.children is None:
            self.children = []


class OutlineTool(Tool):
    """Show the outline (structure) of a file."""

    name = "outline"
    description = "Show the structure of a file (classes, functions, methods)"
    requires_build_mode = False

    # Language detection by extension
    LANGUAGE_MAP = {
        ".py": "python",
        ".js": "javascript",
        ".jsx": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".rs": "rust",
        ".go": "go",
        ".java": "java",
        ".c": "c",
        ".h": "c",
        ".cpp": "cpp",
        ".hpp": "cpp",
        ".rb": "ruby",
    }

    # Patterns for extracting symbols
    PATTERNS = {
        "python": [
            (r"^(\s*)class\s+(\w+)\s*[\(:]", "class"),
            (r"^(\s*)def\s+(\w+)\s*\(", "function"),
            (r"^(\s*)async\s+def\s+(\w+)\s*\(", "async function"),
        ],
        "javascript": [
            (r"^(\s*)class\s+(\w+)\s*[{{\s]", "class"),
            (r"^(\s*)function\s+(\w+)\s*\(", "function"),
            (r"^(\s*)async\s+function\s+(\w+)\s*\(", "async function"),
            (r"^(\s*)(\w+)\s*\([^)]*\)\s*{{", "method"),
            (r"^(\s*)(\w+)\s*:\s*function", "method"),
            (r"^(\s*)const\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>", "arrow function"),
        ],
        "typescript": [
            (r"^(\s*)class\s+(\w+)\s*[{{\s<]", "class"),
            (r"^(\s*)interface\s+(\w+)\s*[{{\s<]", "interface"),
            (r"^(\s*)type\s+(\w+)\s*=", "type"),
            (r"^(\s*)enum\s+(\w+)\s*{{", "enum"),
            (r"^(\s*)function\s+(\w+)\s*[<\(]", "function"),
            (r"^(\s*)async\s+function\s+(\w+)\s*[<\(]", "async function"),
            (r"^(\s*)(?:public|private|protected)?\s*(\w+)\s*\([^)]*\)\s*[{{:]", "method"),
        ],
        "rust": [
            (r"^(\s*)(?:pub\s+)?struct\s+(\w+)\s*[{{\s<]", "struct"),
            (r"^(\s*)(?:pub\s+)?enum\s+(\w+)\s*[{{\s<]", "enum"),
            (r"^(\s*)(?:pub\s+)?trait\s+(\w+)\s*[{{\s<:]", "trait"),
            (r"^(\s*)impl(?:\s+\w+)?\s+(?:for\s+)?(\w+)\s*[{{\s<]", "impl"),
            (r"^(\s*)(?:pub\s+)?(?:async\s+)?fn\s+(\w+)\s*[<\(]", "function"),
            (r"^(\s*)mod\s+(\w+)\s*[{{;]", "module"),
        ],
        "go": [
            (r"^(\s*)type\s+(\w+)\s+struct\s*{{", "struct"),
            (r"^(\s*)type\s+(\w+)\s+interface\s*{{", "interface"),
            (r"^(\s*)func\s+(\w+)\s*\(", "function"),
            (r"^(\s*)func\s+\([^)]+\)\s+(\w+)\s*\(", "method"),
        ],
        "java": [
            (r"^(\s*)(?:public|private|protected)?\s*(?:static)?\s*class\s+(\w+)", "class"),
            (r"^(\s*)(?:public|private|protected)?\s*interface\s+(\w+)", "interface"),
            (r"^(\s*)(?:public|private|protected)?\s*enum\s+(\w+)", "enum"),
            (r"^(\s*)(?:public|private|protected)?\s*(?:static)?\s*\w+\s+(\w+)\s*\(", "method"),
        ],
        "c": [
            (r"^(\s*)struct\s+(\w+)\s*{{", "struct"),
            (r"^(\s*)enum\s+(\w+)\s*{{", "enum"),
            (r"^(\s*)typedef\s+.*\s+(\w+)\s*;", "typedef"),
            (r"^(\s*)(?:static\s+)?(?:inline\s+)?\w+\s*\*?\s*(\w+)\s*\([^;]*$", "function"),
        ],
        "cpp": [
            (r"^(\s*)class\s+(\w+)\s*[{{:]", "class"),
            (r"^(\s*)struct\s+(\w+)\s*[{{:]", "struct"),
            (r"^(\s*)namespace\s+(\w+)\s*{{", "namespace"),
            (r"^(\s*)enum\s+(?:class\s+)?(\w+)\s*{{", "enum"),
            (r"^(\s*)(?:virtual\s+)?(?:static\s+)?(?:inline\s+)?\w+\s*\*?\s*(\w+)\s*\([^;]*$", "function"),
        ],
        "ruby": [
            (r"^(\s*)class\s+(\w+)", "class"),
            (r"^(\s*)module\s+(\w+)", "module"),
            (r"^(\s*)def\s+(\w+)", "method"),
        ],
    }

    def execute(self, path: str) -> ToolResult:
        """Show the outline of a file.

        Args:
            path: Path to the file.

        Returns:
            ToolResult with the file outline.
        """
        try:
            file_path = self._resolve_path(path)
        except ValueError as e:
            return ToolResult.fail(str(e))

        if not file_path.is_file():
            return ToolResult.fail(f"Not a file: {path}")

        # Detect language
        suffix = file_path.suffix
        language = self.LANGUAGE_MAP.get(suffix)
        if not language:
            return ToolResult.fail(f"Unsupported file type: {suffix}")

        patterns = self.PATTERNS.get(language, [])
        if not patterns:
            return ToolResult.fail(f"No outline patterns for: {language}")

        # Compile patterns
        compiled = [(re.compile(p), k) for p, k in patterns]

        # Parse file
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            return ToolResult.fail(f"Could not read file: {e}")

        lines = content.splitlines()
        symbols = []

        for line_num, line in enumerate(lines, 1):
            for pattern, kind in compiled:
                match = pattern.match(line)
                if match:
                    indent_str = match.group(1)
                    name = match.group(2)

                    # Calculate indent level
                    indent = len(indent_str.replace('\t', '    '))

                    symbols.append(Symbol(
                        name=name,
                        kind=kind,
                        line=line_num,
                        indent=indent,
                    ))
                    break

        if not symbols:
            return ToolResult.ok(f"No symbols found in {path}")

        # Build hierarchical structure
        root_symbols = self._build_hierarchy(symbols)

        # Format output
        output_lines = [f"Outline of {path} ({language}):", ""]
        for sym in root_symbols:
            self._format_symbol(sym, output_lines, prefix="")

        output = "\n".join(output_lines)
        return ToolResult.ok(output)

    def _build_hierarchy(self, symbols: list) -> list:
        """Build a hierarchical structure from flat symbol list."""
        if not symbols:
            return []

        root = []
        stack = []  # (symbol, indent)

        for sym in symbols:
            # Pop stack until we find parent
            while stack and stack[-1][1] >= sym.indent:
                stack.pop()

            if stack:
                # Add as child of current top
                stack[-1][0].children.append(sym)
            else:
                # Top-level symbol
                root.append(sym)

            # Push current symbol
            stack.append((sym, sym.indent))

        return root

    def _format_symbol(self, sym: Symbol, lines: list, prefix: str) -> None:
        """Format a symbol and its children."""
        icon = self._get_icon(sym.kind)
        lines.append(f"{prefix}{icon} {sym.name} ({sym.kind}) - line {sym.line}")

        for i, child in enumerate(sym.children):
            is_last = (i == len(sym.children) - 1)
            child_prefix = prefix + ("    " if is_last else "│   ")
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector[:-4]}", )  # Remove connector, we'll add icon
            self._format_symbol(child, lines, child_prefix)

    def _format_symbol(self, sym: Symbol, lines: list, prefix: str, is_last: bool = True) -> None:
        """Format a symbol and its children."""
        icon = self._get_icon(sym.kind)
        connector = "└── " if is_last else "├── "
        if prefix:
            lines.append(f"{prefix}{connector}{icon} {sym.name} ({sym.kind}) ::{sym.line}")
        else:
            lines.append(f"  {icon} {sym.name} ({sym.kind}) ::{sym.line}")

        child_prefix = prefix + ("    " if is_last else "│   ")
        for i, child in enumerate(sym.children):
            child_is_last = (i == len(sym.children) - 1)
            self._format_symbol(child, lines, child_prefix, child_is_last)

    def _get_icon(self, kind: str) -> str:
        """Get a text icon for symbol kind."""
        icons = {
            "class": "[C]",
            "interface": "[I]",
            "struct": "[S]",
            "enum": "[E]",
            "trait": "[T]",
            "type": "[T]",
            "function": "[F]",
            "async function": "[F]",
            "method": "[M]",
            "arrow function": "[F]",
            "module": "[m]",
            "namespace": "[N]",
            "impl": "[i]",
            "typedef": "[t]",
        }
        return icons.get(kind, "[?]")

    def get_schema(self) -> dict:
        """Return JSON schema for LLM function calling."""
        return {
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to outline"
                }
            },
            "required": ["path"]
        }

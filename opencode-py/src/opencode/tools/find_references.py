"""Find references tool - locate where a symbol is used."""

import re
import os
from pathlib import Path
from typing import Optional

from opencode.tools.base import Tool, ToolResult


class FindReferencesTool(Tool):
    """Find all references to a symbol (function, class, variable) in the codebase."""

    name = "find_references"
    description = "Find all locations where a symbol (function, class, variable) is used in the codebase"
    requires_build_mode = False

    # File extensions to search by language
    LANGUAGE_EXTENSIONS = {
        "python": [".py"],
        "javascript": [".js", ".jsx", ".mjs"],
        "typescript": [".ts", ".tsx"],
        "rust": [".rs"],
        "go": [".go"],
        "java": [".java"],
        "c": [".c", ".h"],
        "cpp": [".cpp", ".hpp", ".cc", ".hh", ".cxx"],
        "ruby": [".rb"],
        "php": [".php"],
    }

    # Patterns that indicate a definition (not a reference)
    DEFINITION_PATTERNS = {
        "python": [
            r"^\s*def\s+{symbol}\s*\(",        # function def
            r"^\s*class\s+{symbol}\s*[\(:]",   # class def
            r"^\s*{symbol}\s*=",               # variable assignment at start
            r"^\s*async\s+def\s+{symbol}\s*\(",  # async function
        ],
        "javascript": [
            r"^\s*function\s+{symbol}\s*\(",
            r"^\s*class\s+{symbol}\s*[{{\s]",
            r"^\s*const\s+{symbol}\s*=",
            r"^\s*let\s+{symbol}\s*=",
            r"^\s*var\s+{symbol}\s*=",
            r"^\s*{symbol}\s*:\s*function",
            r"^\s*{symbol}\s*\([^)]*\)\s*{{",  # method shorthand
        ],
        "typescript": [
            r"^\s*function\s+{symbol}\s*[<\(]",
            r"^\s*class\s+{symbol}\s*[{{\s<]",
            r"^\s*const\s+{symbol}\s*[=:]",
            r"^\s*let\s+{symbol}\s*[=:]",
            r"^\s*interface\s+{symbol}\s*[{{\s<]",
            r"^\s*type\s+{symbol}\s*=",
        ],
    }

    # Common extensions to skip
    SKIP_EXTENSIONS = {".pyc", ".pyo", ".so", ".dll", ".exe", ".bin", ".lock"}
    SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".tox"}

    def execute(
        self,
        symbol: str,
        language: Optional[str] = None,
        include_definitions: bool = False,
        max_results: int = 50,
    ) -> ToolResult:
        """Find all references to a symbol.

        Args:
            symbol: The symbol name to search for (function, class, variable).
            language: Optional language filter (python, javascript, etc.).
            include_definitions: If True, include definition sites. Default False.
            max_results: Maximum number of results to return.

        Returns:
            ToolResult with all reference locations.
        """
        if not symbol or not symbol.strip():
            return ToolResult.fail("Symbol name is required")

        symbol = symbol.strip()

        # Determine which extensions to search
        extensions = None
        if language:
            language = language.lower()
            extensions = self.LANGUAGE_EXTENSIONS.get(language)
            if not extensions:
                return ToolResult.fail(
                    f"Unknown language: {language}. "
                    f"Supported: {', '.join(self.LANGUAGE_EXTENSIONS.keys())}"
                )

        # Get definition patterns for filtering
        def_patterns = []
        if not include_definitions and language:
            patterns = self.DEFINITION_PATTERNS.get(language, [])
            def_patterns = [re.compile(p.format(symbol=re.escape(symbol))) for p in patterns]

        # Build regex for symbol usage
        # Match symbol as a whole word (not part of another word)
        symbol_pattern = re.compile(r'\b' + re.escape(symbol) + r'\b')

        # Search files
        results = []
        workspace_root = Path(self.workspace.root if self.workspace else ".")

        for file_path in self._find_files(workspace_root, extensions):
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                lines = content.splitlines()

                for line_num, line in enumerate(lines, 1):
                    if symbol_pattern.search(line):
                        # Check if this is a definition (skip if not including definitions)
                        if def_patterns and any(p.match(line) for p in def_patterns):
                            continue

                        # Skip comments (basic heuristic)
                        stripped = line.lstrip()
                        if stripped.startswith('#') or stripped.startswith('//'):
                            continue

                        rel_path = file_path.relative_to(workspace_root)
                        results.append({
                            "file": str(rel_path),
                            "line": line_num,
                            "content": line.strip()[:120],  # Truncate long lines
                        })

                        if len(results) >= max_results:
                            break

            except Exception:
                continue

            if len(results) >= max_results:
                break

        if not results:
            return ToolResult.ok(f"No references found for '{symbol}'")

        # Format output
        output_lines = [f"Found {len(results)} reference(s) to '{symbol}':", ""]
        for ref in results:
            output_lines.append(f"  {ref['file']}:{ref['line']}")
            output_lines.append(f"    {ref['content']}")
            output_lines.append("")

        if len(results) >= max_results:
            output_lines.append(f"  ... (showing first {max_results} results)")

        output = "\n".join(output_lines)
        return ToolResult.ok(output)

    def _find_files(self, root: Path, extensions: Optional[list] = None):
        """Recursively find files to search."""
        for item in root.iterdir():
            if item.name.startswith('.') and item.name != '.':
                continue
            if item.name in self.SKIP_DIRS:
                continue

            if item.is_dir():
                yield from self._find_files(item, extensions)
            elif item.is_file():
                if item.suffix in self.SKIP_EXTENSIONS:
                    continue
                if extensions and item.suffix not in extensions:
                    continue
                yield item

    def get_schema(self) -> dict:
        """Return JSON schema for LLM function calling."""
        return {
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The symbol name to find references for (function, class, variable)"
                },
                "language": {
                    "type": "string",
                    "description": "Optional language filter (python, javascript, typescript, rust, go, java, c, cpp, ruby, php)",
                    "enum": list(self.LANGUAGE_EXTENSIONS.keys())
                },
                "include_definitions": {
                    "type": "boolean",
                    "description": "Include definition sites in results (default: false)",
                    "default": False
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results to return (default: 50)",
                    "default": 50
                }
            },
            "required": ["symbol"]
        }

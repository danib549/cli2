"""Find definition tool - locate where a symbol is defined."""

import re
from pathlib import Path
from typing import Optional

from opencode.tools.base import Tool, ToolResult


class FindDefinitionTool(Tool):
    """Find where a symbol (function, class, variable) is defined."""

    name = "find_definition"
    description = "Find where a symbol (function, class, variable) is defined in the codebase"
    requires_build_mode = False

    # File extensions by language
    LANGUAGE_EXTENSIONS = {
        "python": [".py"],
        "javascript": [".js", ".jsx", ".mjs"],
        "typescript": [".ts", ".tsx"],
        "rust": [".rs"],
        "go": [".go"],
        "java": [".java"],
        "c": [".c", ".h"],
        "cpp": [".cpp", ".hpp", ".cc", ".hh", ".cxx", ".h"],
        "ruby": [".rb"],
        "php": [".php"],
    }

    # Patterns that indicate a definition
    DEFINITION_PATTERNS = {
        "python": [
            (r"^\s*def\s+{symbol}\s*\(", "function"),
            (r"^\s*async\s+def\s+{symbol}\s*\(", "async function"),
            (r"^\s*class\s+{symbol}\s*[\(:]", "class"),
            (r"^{symbol}\s*=", "variable"),  # top-level assignment
            (r"^\s+{symbol}\s*=\s*", "attribute"),  # indented assignment (class attr, etc)
        ],
        "javascript": [
            (r"^\s*function\s+{symbol}\s*\(", "function"),
            (r"^\s*async\s+function\s+{symbol}\s*\(", "async function"),
            (r"^\s*class\s+{symbol}\s*[{{\s]", "class"),
            (r"^\s*const\s+{symbol}\s*=", "const"),
            (r"^\s*let\s+{symbol}\s*=", "let"),
            (r"^\s*var\s+{symbol}\s*=", "var"),
            (r"^\s*{symbol}\s*:\s*function", "method"),
            (r"^\s*{symbol}\s*\([^)]*\)\s*{{", "method"),
            (r"^\s*export\s+(default\s+)?function\s+{symbol}", "exported function"),
            (r"^\s*export\s+(default\s+)?class\s+{symbol}", "exported class"),
            (r"^\s*export\s+(const|let|var)\s+{symbol}", "exported variable"),
        ],
        "typescript": [
            (r"^\s*function\s+{symbol}\s*[<\(]", "function"),
            (r"^\s*async\s+function\s+{symbol}\s*[<\(]", "async function"),
            (r"^\s*class\s+{symbol}\s*[{{\s<]", "class"),
            (r"^\s*interface\s+{symbol}\s*[{{\s<]", "interface"),
            (r"^\s*type\s+{symbol}\s*[<=]", "type alias"),
            (r"^\s*enum\s+{symbol}\s*{{", "enum"),
            (r"^\s*const\s+{symbol}\s*[=:]", "const"),
            (r"^\s*let\s+{symbol}\s*[=:]", "let"),
            (r"^\s*export\s+(default\s+)?function\s+{symbol}", "exported function"),
            (r"^\s*export\s+(default\s+)?class\s+{symbol}", "exported class"),
            (r"^\s*export\s+interface\s+{symbol}", "exported interface"),
            (r"^\s*export\s+type\s+{symbol}", "exported type"),
        ],
        "rust": [
            (r"^\s*fn\s+{symbol}\s*[<\(]", "function"),
            (r"^\s*pub\s+fn\s+{symbol}\s*[<\(]", "public function"),
            (r"^\s*async\s+fn\s+{symbol}\s*[<\(]", "async function"),
            (r"^\s*struct\s+{symbol}\s*[{{\s<]", "struct"),
            (r"^\s*enum\s+{symbol}\s*[{{\s<]", "enum"),
            (r"^\s*trait\s+{symbol}\s*[{{\s<:]", "trait"),
            (r"^\s*impl\s+{symbol}\s*[{{\s<]", "impl"),
            (r"^\s*type\s+{symbol}\s*=", "type alias"),
            (r"^\s*const\s+{symbol}\s*:", "const"),
            (r"^\s*static\s+{symbol}\s*:", "static"),
            (r"^\s*mod\s+{symbol}\s*[{{;]", "module"),
        ],
        "go": [
            (r"^\s*func\s+{symbol}\s*\(", "function"),
            (r"^\s*func\s+\([^)]+\)\s+{symbol}\s*\(", "method"),
            (r"^\s*type\s+{symbol}\s+struct\s*{{", "struct"),
            (r"^\s*type\s+{symbol}\s+interface\s*{{", "interface"),
            (r"^\s*type\s+{symbol}\s+", "type"),
            (r"^\s*var\s+{symbol}\s+", "var"),
            (r"^\s*const\s+{symbol}\s+", "const"),
        ],
        "java": [
            (r"^\s*(public|private|protected)?\s*(static)?\s*class\s+{symbol}", "class"),
            (r"^\s*(public|private|protected)?\s*(static)?\s*interface\s+{symbol}", "interface"),
            (r"^\s*(public|private|protected)?\s*(static)?\s*enum\s+{symbol}", "enum"),
            (r"^\s*(public|private|protected)?\s*(static)?\s*\w+\s+{symbol}\s*\(", "method"),
        ],
    }

    SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".tox", "target"}

    def execute(
        self,
        symbol: str,
        language: Optional[str] = None,
    ) -> ToolResult:
        """Find where a symbol is defined.

        Args:
            symbol: The symbol name to find the definition of.
            language: Optional language filter.

        Returns:
            ToolResult with definition location(s).
        """
        if not symbol or not symbol.strip():
            return ToolResult.fail("Symbol name is required")

        symbol = symbol.strip()

        # Determine which extensions and patterns to use
        if language:
            language = language.lower()
            extensions = self.LANGUAGE_EXTENSIONS.get(language)
            if not extensions:
                return ToolResult.fail(f"Unknown language: {language}")
            patterns = self.DEFINITION_PATTERNS.get(language, [])
            search_config = [(language, extensions, patterns)]
        else:
            # Search all languages
            search_config = [
                (lang, exts, self.DEFINITION_PATTERNS.get(lang, []))
                for lang, exts in self.LANGUAGE_EXTENSIONS.items()
            ]

        # Compile patterns
        compiled_configs = []
        for lang, exts, patterns in search_config:
            compiled = [
                (re.compile(p.format(symbol=re.escape(symbol)), re.IGNORECASE), kind)
                for p, kind in patterns
            ]
            compiled_configs.append((lang, exts, compiled))

        # Search files
        results = []
        workspace_root = Path(self.workspace.root if self.workspace else ".")

        for file_path in self._find_files(workspace_root):
            suffix = file_path.suffix

            # Find matching language config
            for lang, exts, patterns in compiled_configs:
                if suffix not in exts:
                    continue

                try:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    lines = content.splitlines()

                    for line_num, line in enumerate(lines, 1):
                        for pattern, kind in patterns:
                            if pattern.search(line):
                                rel_path = file_path.relative_to(workspace_root)
                                results.append({
                                    "file": str(rel_path),
                                    "line": line_num,
                                    "kind": kind,
                                    "language": lang,
                                    "content": line.strip()[:150],
                                })
                                break  # One match per line is enough

                except Exception:
                    continue

        if not results:
            return ToolResult.ok(f"No definition found for '{symbol}'")

        # Sort by specificity (class/function defs before variable assignments)
        priority = {"class": 0, "function": 1, "async function": 1, "interface": 2,
                   "type": 3, "method": 4, "const": 5, "variable": 6, "attribute": 7}
        results.sort(key=lambda r: priority.get(r["kind"], 10))

        # Format output
        output_lines = [f"Found {len(results)} definition(s) for '{symbol}':", ""]
        for ref in results:
            output_lines.append(f"  [{ref['kind']}] {ref['file']}:{ref['line']}")
            output_lines.append(f"    {ref['content']}")
            output_lines.append("")

        output = "\n".join(output_lines)
        return ToolResult.ok(output)

    def _find_files(self, root: Path):
        """Recursively find source files."""
        try:
            for item in root.iterdir():
                if item.name.startswith('.'):
                    continue
                if item.name in self.SKIP_DIRS:
                    continue

                if item.is_dir():
                    yield from self._find_files(item)
                elif item.is_file():
                    # Check if it's a source file
                    for exts in self.LANGUAGE_EXTENSIONS.values():
                        if item.suffix in exts:
                            yield item
                            break
        except PermissionError:
            pass

    def get_schema(self) -> dict:
        """Return JSON schema for LLM function calling."""
        return {
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "The symbol name to find the definition of (function, class, variable, type)"
                },
                "language": {
                    "type": "string",
                    "description": "Optional language filter",
                    "enum": list(self.LANGUAGE_EXTENSIONS.keys())
                }
            },
            "required": ["symbol"]
        }

"""Find symbols tool - search for function/class/variable names."""

import re
from pathlib import Path
from typing import Optional

from opencode.tools.base import Tool, ToolResult


class FindSymbolsTool(Tool):
    """Find all symbols (functions, classes, variables) matching a query."""

    name = "find_symbols"
    description = "Search for symbol names (functions, classes, types) in the codebase"
    requires_build_mode = False

    # Symbol extraction patterns by language
    SYMBOL_PATTERNS = {
        "python": [
            (r"^\s*def\s+(\w+)\s*\(", "function"),
            (r"^\s*async\s+def\s+(\w+)\s*\(", "async function"),
            (r"^\s*class\s+(\w+)\s*[\(:]", "class"),
            (r"^(\w+)\s*=", "variable"),
        ],
        "javascript": [
            (r"^\s*function\s+(\w+)\s*\(", "function"),
            (r"^\s*async\s+function\s+(\w+)\s*\(", "async function"),
            (r"^\s*class\s+(\w+)\s*[{{\s]", "class"),
            (r"^\s*const\s+(\w+)\s*=", "const"),
            (r"^\s*let\s+(\w+)\s*=", "let"),
            (r"^\s*var\s+(\w+)\s*=", "var"),
            (r"^\s*export\s+(?:default\s+)?function\s+(\w+)", "exported function"),
            (r"^\s*export\s+(?:default\s+)?class\s+(\w+)", "exported class"),
        ],
        "typescript": [
            (r"^\s*function\s+(\w+)\s*[<\(]", "function"),
            (r"^\s*async\s+function\s+(\w+)\s*[<\(]", "async function"),
            (r"^\s*class\s+(\w+)\s*[{{\s<]", "class"),
            (r"^\s*interface\s+(\w+)\s*[{{\s<]", "interface"),
            (r"^\s*type\s+(\w+)\s*[<=]", "type"),
            (r"^\s*enum\s+(\w+)\s*{{", "enum"),
            (r"^\s*const\s+(\w+)\s*[=:]", "const"),
            (r"^\s*export\s+(?:default\s+)?function\s+(\w+)", "exported function"),
            (r"^\s*export\s+(?:default\s+)?class\s+(\w+)", "exported class"),
            (r"^\s*export\s+interface\s+(\w+)", "exported interface"),
            (r"^\s*export\s+type\s+(\w+)", "exported type"),
        ],
        "rust": [
            (r"^\s*(?:pub\s+)?fn\s+(\w+)\s*[<\(]", "function"),
            (r"^\s*(?:pub\s+)?struct\s+(\w+)\s*[{{\s<]", "struct"),
            (r"^\s*(?:pub\s+)?enum\s+(\w+)\s*[{{\s<]", "enum"),
            (r"^\s*(?:pub\s+)?trait\s+(\w+)\s*[{{\s<:]", "trait"),
            (r"^\s*type\s+(\w+)\s*=", "type alias"),
            (r"^\s*(?:pub\s+)?mod\s+(\w+)\s*[{{;]", "module"),
        ],
        "go": [
            (r"^\s*func\s+(\w+)\s*\(", "function"),
            (r"^\s*func\s+\([^)]+\)\s+(\w+)\s*\(", "method"),
            (r"^\s*type\s+(\w+)\s+struct", "struct"),
            (r"^\s*type\s+(\w+)\s+interface", "interface"),
        ],
        "java": [
            (r"^\s*(?:public|private|protected)?\s*(?:static)?\s*class\s+(\w+)", "class"),
            (r"^\s*(?:public|private|protected)?\s*interface\s+(\w+)", "interface"),
            (r"^\s*(?:public|private|protected)?\s*enum\s+(\w+)", "enum"),
        ],
    }

    LANGUAGE_EXTENSIONS = {
        "python": [".py"],
        "javascript": [".js", ".jsx", ".mjs"],
        "typescript": [".ts", ".tsx"],
        "rust": [".rs"],
        "go": [".go"],
        "java": [".java"],
    }

    SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".tox", "target"}

    def execute(
        self,
        query: str = "",
        kind: Optional[str] = None,
        language: Optional[str] = None,
        max_results: int = 100,
    ) -> ToolResult:
        """Find symbols matching a query.

        Args:
            query: Optional pattern to filter symbols (supports wildcards * and ?).
            kind: Optional filter by kind (function, class, interface, type, etc.).
            language: Optional language filter.
            max_results: Maximum number of results.

        Returns:
            ToolResult with matching symbols.
        """
        # Convert query to regex pattern
        query_pattern = None
        if query:
            # Convert glob-style wildcards to regex
            pattern = query.replace("*", ".*").replace("?", ".")
            query_pattern = re.compile(pattern, re.IGNORECASE)

        # Determine which languages to search
        if language:
            language = language.lower()
            if language not in self.SYMBOL_PATTERNS:
                return ToolResult.fail(f"Unknown language: {language}")
            languages = [language]
        else:
            languages = list(self.SYMBOL_PATTERNS.keys())

        # Compile patterns
        compiled_patterns = {}
        for lang in languages:
            compiled_patterns[lang] = [
                (re.compile(p), k) for p, k in self.SYMBOL_PATTERNS[lang]
            ]

        # Search files
        results = []
        workspace_root = Path(self.workspace.root if self.workspace else ".")

        for file_path in self._find_files(workspace_root):
            suffix = file_path.suffix

            # Find matching language
            for lang in languages:
                if suffix not in self.LANGUAGE_EXTENSIONS.get(lang, []):
                    continue

                try:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')
                    lines = content.splitlines()

                    for line_num, line in enumerate(lines, 1):
                        for pattern, symbol_kind in compiled_patterns[lang]:
                            match = pattern.search(line)
                            if match:
                                symbol_name = match.group(1)

                                # Apply query filter
                                if query_pattern and not query_pattern.search(symbol_name):
                                    continue

                                # Apply kind filter
                                if kind and kind.lower() not in symbol_kind.lower():
                                    continue

                                rel_path = file_path.relative_to(workspace_root)
                                results.append({
                                    "name": symbol_name,
                                    "kind": symbol_kind,
                                    "file": str(rel_path),
                                    "line": line_num,
                                    "language": lang,
                                })

                                if len(results) >= max_results:
                                    break
                        if len(results) >= max_results:
                            break

                except Exception:
                    continue

                if len(results) >= max_results:
                    break
            if len(results) >= max_results:
                break

        if not results:
            msg = "No symbols found"
            if query:
                msg += f" matching '{query}'"
            return ToolResult.ok(msg)

        # Group by kind for cleaner output
        by_kind = {}
        for r in results:
            k = r["kind"]
            if k not in by_kind:
                by_kind[k] = []
            by_kind[k].append(r)

        # Format output
        output_lines = [f"Found {len(results)} symbol(s):", ""]

        for symbol_kind in sorted(by_kind.keys()):
            items = by_kind[symbol_kind]
            output_lines.append(f"  [{symbol_kind}] ({len(items)})")
            for item in items[:20]:  # Limit per category
                output_lines.append(f"    {item['name']} - {item['file']}:{item['line']}")
            if len(items) > 20:
                output_lines.append(f"    ... and {len(items) - 20} more")
            output_lines.append("")

        if len(results) >= max_results:
            output_lines.append(f"  (showing first {max_results} results)")

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
                "query": {
                    "type": "string",
                    "description": "Pattern to filter symbols (supports * and ? wildcards). Empty to list all symbols."
                },
                "kind": {
                    "type": "string",
                    "description": "Filter by symbol kind (function, class, interface, type, etc.)"
                },
                "language": {
                    "type": "string",
                    "description": "Optional language filter",
                    "enum": list(self.SYMBOL_PATTERNS.keys())
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum number of results (default: 100)",
                    "default": 100
                }
            },
            "required": []
        }

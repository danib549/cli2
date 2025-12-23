"""Rename symbol tool - rename a symbol across multiple files."""

import re
from pathlib import Path
from typing import Optional

from opencode.tools.base import Tool, ToolResult


class RenameSymbolTool(Tool):
    """Rename a symbol across multiple files in the codebase."""

    name = "rename_symbol"
    description = "Rename a symbol (function, class, variable) across all files in the codebase"
    requires_build_mode = True  # This modifies files

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

    SKIP_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", ".tox", "target"}

    def execute(
        self,
        old_name: str,
        new_name: str,
        language: Optional[str] = None,
        dry_run: bool = True,
    ) -> ToolResult:
        """Rename a symbol across all files.

        Args:
            old_name: The current symbol name.
            new_name: The new symbol name.
            language: Optional language filter (only rename in files of this language).
            dry_run: If True (default), only show what would be changed without making changes.

        Returns:
            ToolResult with list of changes made/to be made.
        """
        self._check_mode()

        if not old_name or not old_name.strip():
            return ToolResult.fail("old_name is required")
        if not new_name or not new_name.strip():
            return ToolResult.fail("new_name is required")

        old_name = old_name.strip()
        new_name = new_name.strip()

        # Validate names
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', old_name):
            return ToolResult.fail(f"Invalid symbol name: {old_name}")
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', new_name):
            return ToolResult.fail(f"Invalid symbol name: {new_name}")

        if old_name == new_name:
            return ToolResult.fail("old_name and new_name are the same")

        # Determine extensions to search
        extensions = None
        if language:
            language = language.lower()
            extensions = self.LANGUAGE_EXTENSIONS.get(language)
            if not extensions:
                return ToolResult.fail(f"Unknown language: {language}")

        # Build regex for whole-word match
        pattern = re.compile(r'\b' + re.escape(old_name) + r'\b')

        # Create checkpoint before making changes
        if not dry_run:
            self._checkpoint(f"Before rename: {old_name} -> {new_name}")

        # Search and replace
        workspace_root = Path(self.workspace.root if self.workspace else ".")
        changes = []

        for file_path in self._find_files(workspace_root, extensions):
            try:
                content = file_path.read_text(encoding='utf-8')

                # Check if file contains the symbol
                if not pattern.search(content):
                    continue

                # Count occurrences per line
                lines = content.splitlines()
                file_changes = []

                for line_num, line in enumerate(lines, 1):
                    matches = list(pattern.finditer(line))
                    if matches:
                        # Skip if in comment or string (basic heuristic)
                        stripped = line.lstrip()
                        if stripped.startswith('#') or stripped.startswith('//'):
                            continue

                        new_line = pattern.sub(new_name, line)
                        file_changes.append({
                            "line": line_num,
                            "old": line.strip()[:80],
                            "new": new_line.strip()[:80],
                            "count": len(matches),
                        })

                if file_changes:
                    rel_path = file_path.relative_to(workspace_root)
                    changes.append({
                        "file": str(rel_path),
                        "changes": file_changes,
                        "path": file_path,
                    })

                    # Actually make changes if not dry run
                    if not dry_run:
                        new_content = pattern.sub(new_name, content)
                        file_path.write_text(new_content, encoding='utf-8')

            except Exception as e:
                continue

        if not changes:
            return ToolResult.ok(f"No occurrences of '{old_name}' found")

        # Format output
        total_changes = sum(sum(c["count"] for c in f["changes"]) for f in changes)
        action = "Would rename" if dry_run else "Renamed"

        output_lines = [
            f"{action} '{old_name}' to '{new_name}'",
            f"Found {total_changes} occurrence(s) in {len(changes)} file(s):",
            ""
        ]

        for file_info in changes:
            output_lines.append(f"  {file_info['file']}:")
            for change in file_info["changes"][:5]:  # Limit shown per file
                output_lines.append(f"    Line {change['line']}: {change['old']}")
                output_lines.append(f"           -> {change['new']}")
            if len(file_info["changes"]) > 5:
                output_lines.append(f"    ... and {len(file_info['changes']) - 5} more changes")
            output_lines.append("")

        if dry_run:
            output_lines.append("[DRY RUN] No changes made. Set dry_run=false to apply changes.")

        output = "\n".join(output_lines)
        return ToolResult.ok(output)

    def _find_files(self, root: Path, extensions: Optional[list] = None):
        """Recursively find source files."""
        try:
            for item in root.iterdir():
                if item.name.startswith('.'):
                    continue
                if item.name in self.SKIP_DIRS:
                    continue

                if item.is_dir():
                    yield from self._find_files(item, extensions)
                elif item.is_file():
                    if extensions:
                        if item.suffix in extensions:
                            yield item
                    else:
                        # Check all known extensions
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
                "old_name": {
                    "type": "string",
                    "description": "The current symbol name to rename"
                },
                "new_name": {
                    "type": "string",
                    "description": "The new symbol name"
                },
                "language": {
                    "type": "string",
                    "description": "Optional language filter",
                    "enum": list(self.LANGUAGE_EXTENSIONS.keys())
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "If true (default), only show what would change without making changes",
                    "default": True
                }
            },
            "required": ["old_name", "new_name"]
        }

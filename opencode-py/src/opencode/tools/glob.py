"""Glob tool for finding files by pattern."""

from pathlib import Path

from opencode.tools.base import Tool, ToolResult


class GlobTool(Tool):
    """Find files matching a glob pattern."""

    name = "glob"
    description = "Find files matching a glob pattern (e.g., '**/*.py', 'src/**/*.ts')"
    requires_build_mode = False  # Safe read-only operation

    def execute(self, pattern: str, path: str = None) -> ToolResult:
        """Find files matching a glob pattern.

        Args:
            pattern: Glob pattern to match (e.g., '**/*.py', 'src/*.ts').
            path: Optional directory to search in (defaults to workspace root).

        Returns:
            ToolResult with list of matching files.
        """
        try:
            # Determine search root
            if path:
                search_root = self._resolve_path(path)
            elif self.workspace and self.workspace.is_initialized:
                search_root = self.workspace.root
            else:
                search_root = Path.cwd()

            if not search_root.is_dir():
                return ToolResult.fail(f"Not a directory: {search_root}")

            # Find matching files
            matches = list(search_root.glob(pattern))

            # Filter to only files (not directories) and exclude .git
            files = [
                f for f in matches
                if f.is_file() and '.git' not in f.parts
            ]

            # Sort by path
            files.sort()

            # Limit results to prevent overwhelming output
            max_results = 50
            truncated = len(files) > max_results

            if truncated:
                files = files[:max_results]

            # Format output
            if not files:
                return ToolResult.ok(f"No files found matching '{pattern}'")

            # Show relative paths
            output_lines = []
            for f in files:
                try:
                    rel_path = f.relative_to(search_root)
                except ValueError:
                    rel_path = f
                output_lines.append(str(rel_path))

            output = "\n".join(output_lines)

            if truncated:
                output += f"\n\n... and more (showing first {max_results} results)"

            # Show colored header
            header = f"\033[34mFound {len(files)} file(s) matching '{pattern}':\033[0m\n"
            return ToolResult.ok(header + output)

        except Exception as e:
            return ToolResult.fail(str(e))

    def get_schema(self) -> dict:
        """Return JSON schema for LLM function calling."""
        return {
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match files (e.g., '**/*.py', 'src/**/*.ts', '*.md')"
                },
                "path": {
                    "type": "string",
                    "description": "Optional directory to search in (defaults to workspace root)"
                }
            },
            "required": ["pattern"]
        }

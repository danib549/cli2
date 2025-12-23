"""Read file tool."""

from pathlib import Path

from opencode.tools.base import Tool, ToolResult


# Maximum lines to display to user (full content still sent to LLM)
MAX_DISPLAY_LINES = 10


class ReadTool(Tool):
    """Read file contents with optional line range."""

    name = "read"
    description = "Read the contents of a file, optionally specifying a line range"
    requires_build_mode = False

    def execute(self, path: str, lines: str = None) -> ToolResult:
        """Read a file's contents.

        Args:
            path: Path to the file.
            lines: Optional line range (e.g., "10-20" or "10").

        Returns:
            ToolResult with file contents.
        """
        self._check_mode()

        try:
            file_path = self._resolve_path(path)
        except ValueError as e:
            return ToolResult.fail(str(e))

        if not file_path.exists():
            return ToolResult.fail(f"File not found: {path}")

        if not file_path.is_file():
            return ToolResult.fail(f"Not a file: {path}")

        try:
            content = file_path.read_text(encoding='utf-8')
            file_lines = content.splitlines()
            total_lines = len(file_lines)

            if lines:
                start, end = self._parse_line_range(lines, total_lines)
                selected_lines = file_lines[start:end]
                numbered = [
                    f"{i + start + 1:4d} | {line}"
                    for i, line in enumerate(selected_lines)
                ]
            else:
                numbered = [
                    f"{i + 1:4d} | {line}"
                    for i, line in enumerate(file_lines)
                ]

            # Full output for LLM
            full_output = "\n".join(numbered)

            # Truncated display for user
            if len(numbered) > MAX_DISPLAY_LINES:
                preview = "\n".join(numbered[:MAX_DISPLAY_LINES])
                remaining = len(numbered) - MAX_DISPLAY_LINES
                print(f"\033[34m> Reading {path} ({total_lines} lines)\033[0m")
                print(preview)
                print(f"\033[90m   ... ({remaining} more lines)\033[0m")
            else:
                print(f"\033[34m> Reading {path} ({total_lines} lines)\033[0m")
                print(full_output)

            # Return full content to LLM (don't print again)
            return ToolResult(success=True, output="", _llm_output=full_output)

        except Exception as e:
            return ToolResult.fail(str(e))

    def _parse_line_range(self, lines: str, total: int) -> tuple[int, int]:
        """Parse a line range like '10-20' or '10'."""
        if "-" in lines:
            parts = lines.split("-")
            start = int(parts[0]) - 1  # Convert to 0-indexed
            end = int(parts[1])
        else:
            start = int(lines) - 1
            end = start + 1
        return max(0, start), min(total, end)

    def get_schema(self) -> dict:
        """Return JSON schema for LLM function calling."""
        return {
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to read"
                },
                "lines": {
                    "type": "string",
                    "description": "Optional line range (e.g., '10-20' or '10')"
                }
            },
            "required": ["path"]
        }

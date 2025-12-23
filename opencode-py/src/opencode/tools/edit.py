"""Edit file tool (patch-based find and replace)."""

from pathlib import Path

from opencode.tools.base import Tool, ToolResult


def generate_diff(old_string: str, new_string: str, path: str) -> str:
    """Generate a git-style diff display."""
    old_lines = old_string.splitlines(keepends=True)
    new_lines = new_string.splitlines(keepends=True)

    diff_lines = [
        f"\033[1m--- {path}\033[0m",
        f"\033[1m+++ {path}\033[0m",
    ]

    # Show removed lines (red)
    for line in old_lines:
        line_clean = line.rstrip('\n\r')
        diff_lines.append(f"\033[31m- {line_clean}\033[0m")

    # Show added lines (green)
    for line in new_lines:
        line_clean = line.rstrip('\n\r')
        diff_lines.append(f"\033[32m+ {line_clean}\033[0m")

    return "\n".join(diff_lines)


class EditTool(Tool):
    """Edit file via find and replace."""

    name = "edit"
    description = "Edit a file by finding and replacing a specific string"
    requires_build_mode = True

    def execute(
        self,
        path: str,
        old_string: str,
        new_string: str
    ) -> ToolResult:
        """Edit a file by replacing old_string with new_string.

        Args:
            path: Path to the file.
            old_string: Text to find (must be unique in file).
            new_string: Text to replace with.

        Returns:
            ToolResult indicating success or failure.
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

            if old_string not in content:
                return ToolResult.fail(
                    f"String not found in {path}: '{old_string[:50]}...'"
                )

            # Count occurrences - must be unique
            count = content.count(old_string)
            if count > 1:
                return ToolResult.fail(
                    f"Ambiguous: '{old_string[:50]}...' found {count} times. "
                    "Provide more context to make it unique."
                )

            # Checkpoint before edit
            self._checkpoint(f"Before edit: {path}")

            # Generate diff for display
            diff = generate_diff(old_string, new_string, path)

            # Perform replacement
            new_content = content.replace(old_string, new_string, 1)
            file_path.write_text(new_content, encoding='utf-8')

            # Return with diff output
            return ToolResult.ok(f"Edited {path}\n\n{diff}")

        except Exception as e:
            return ToolResult.fail(str(e))

    def get_schema(self) -> dict:
        """Return JSON schema for LLM function calling."""
        return {
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to edit"
                },
                "old_string": {
                    "type": "string",
                    "description": "The exact string to find and replace (must be unique in file)"
                },
                "new_string": {
                    "type": "string",
                    "description": "The string to replace it with"
                }
            },
            "required": ["path", "old_string", "new_string"]
        }

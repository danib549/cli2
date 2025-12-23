"""Write file tool (create or overwrite)."""

import difflib
from pathlib import Path

from opencode.tools.base import Tool, ToolResult


def generate_unified_diff(old_content: str, new_content: str, path: str) -> str:
    """Generate a git-style unified diff between old and new content."""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)

    # Ensure lines end with newline for proper diff formatting
    if old_lines and not old_lines[-1].endswith('\n'):
        old_lines[-1] += '\n'
    if new_lines and not new_lines[-1].endswith('\n'):
        new_lines[-1] += '\n'

    diff = difflib.unified_diff(
        old_lines,
        new_lines,
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm=''
    )

    diff_lines = []
    for line in diff:
        line = line.rstrip('\n')
        if line.startswith('---') or line.startswith('+++'):
            diff_lines.append(f"\033[1m{line}\033[0m")
        elif line.startswith('-'):
            diff_lines.append(f"\033[31m{line}\033[0m")
        elif line.startswith('+'):
            diff_lines.append(f"\033[32m{line}\033[0m")
        elif line.startswith('@@'):
            diff_lines.append(f"\033[36m{line}\033[0m")
        else:
            diff_lines.append(line)

    return '\n'.join(diff_lines)


class WriteTool(Tool):
    """Write content to a file (create or overwrite)."""

    name = "write"
    description = "Write content to a file, creating it if it doesn't exist or overwriting if it does"
    requires_build_mode = True

    def execute(self, path: str, content: str) -> ToolResult:
        """Write content to a file.

        Args:
            path: Path to the file.
            content: Content to write.

        Returns:
            ToolResult indicating success or failure.
        """
        self._check_mode()

        try:
            file_path = self._resolve_path(path)
        except ValueError as e:
            return ToolResult.fail(str(e))

        try:
            # Create parent directories if needed
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # Check if overwriting
            is_new = not file_path.exists()
            old_content = ""
            if not is_new:
                try:
                    old_content = file_path.read_text(encoding='utf-8')
                except Exception:
                    old_content = ""

            # Checkpoint before write
            action = "create" if is_new else "overwrite"
            self._checkpoint(f"Before {action}: {path}")

            # Write file (UTF-8 for cross-platform Unicode support)
            file_path.write_text(content, encoding='utf-8')

            # Show output based on create vs overwrite
            if is_new:
                print(f"\033[32m+ Creating {path}\033[0m")
                # Show preview of new content
                lines = content.splitlines()
                preview_lines = min(5, len(lines))
                preview = "\n".join(f"  {line}" for line in lines[:preview_lines])
                if len(lines) > preview_lines:
                    preview += f"\n  ... ({len(lines) - preview_lines} more lines)"
                return ToolResult.ok(f"Created {path} ({len(content)} bytes)\n\n{preview}")
            else:
                print(f"\033[33m~ Overwriting {path}\033[0m")
                # Show git-style diff
                diff_output = generate_unified_diff(old_content, content, path)
                if diff_output:
                    print(diff_output)
                    return ToolResult.ok(f"Overwrote {path} ({len(content)} bytes)\n\n{diff_output}")
                else:
                    return ToolResult.ok(f"Overwrote {path} ({len(content)} bytes, no changes)")

        except Exception as e:
            return ToolResult.fail(str(e))

    def get_schema(self) -> dict:
        """Return JSON schema for LLM function calling."""
        return {
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to write"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file"
                }
            },
            "required": ["path", "content"]
        }

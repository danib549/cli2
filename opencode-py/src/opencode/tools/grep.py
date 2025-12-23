"""Grep tool for searching file contents."""

import re
from pathlib import Path
from typing import Literal

from opencode.tools.base import Tool, ToolResult
from opencode.style import bold, dim, yellow, blue


class GrepTool(Tool):
    """Search for patterns in file contents."""

    name = "grep"
    description = "Search for a pattern in files (like grep). Returns matching files and lines."
    requires_build_mode = False  # Safe read-only operation

    # File extensions to search (text files)
    SEARCHABLE_EXTENSIONS = {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".vue", ".svelte",
        ".html", ".css", ".scss", ".sass", ".less",
        ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
        ".md", ".txt", ".rst", ".tex",
        ".sh", ".bash", ".zsh", ".fish",
        ".c", ".cpp", ".h", ".hpp", ".cc",
        ".java", ".kt", ".scala", ".groovy",
        ".go", ".rs", ".rb", ".php", ".pl",
        ".sql", ".graphql", ".prisma",
        ".xml", ".svg",
        ".env", ".gitignore", ".dockerignore",
        "Makefile", "Dockerfile", "Jenkinsfile",
    }

    # Files without extensions to search
    SEARCHABLE_NAMES = {
        "Makefile", "Dockerfile", "Jenkinsfile", "Vagrantfile",
        "Gemfile", "Rakefile", "Procfile",
        ".gitignore", ".dockerignore", ".env",
    }

    def execute(
        self,
        pattern: str,
        path: str = None,
        file_pattern: str = None,
        ignore_case: bool = False,
        max_results: int = 50,
        output_mode: Literal["content", "files_with_matches", "count"] = "content",
        context_before: int = 0,
        context_after: int = 0,
        context: int = 0,
        multiline: bool = False,
    ) -> ToolResult:
        """Search for a pattern in files.

        Args:
            pattern: Regex pattern to search for.
            path: Optional directory to search in (defaults to workspace root).
            file_pattern: Optional glob pattern to filter files (e.g., '*.py').
            ignore_case: Whether to ignore case in matching.
            max_results: Maximum number of results to return.
            output_mode: Output format:
                - "content": Show matching lines with line numbers (default)
                - "files_with_matches": Only show file paths that match
                - "count": Show match count per file
            context_before: Number of lines to show before each match (-B).
            context_after: Number of lines to show after each match (-A).
            context: Number of lines to show before AND after each match (-C).
            multiline: Enable multiline matching (pattern can span multiple lines).

        Returns:
            ToolResult with matching files and lines.
        """
        try:
            # Determine search root
            if path:
                search_root = self._resolve_path(path)
            elif self.workspace and self.workspace.is_initialized:
                search_root = self.workspace.root
            else:
                search_root = Path.cwd()

            if not search_root.exists():
                return ToolResult.fail(f"Path not found: {search_root}")

            # Handle context parameter (overrides individual before/after)
            if context > 0:
                context_before = context
                context_after = context

            # Compile regex
            flags = re.IGNORECASE if ignore_case else 0
            if multiline:
                flags |= re.MULTILINE | re.DOTALL
            try:
                regex = re.compile(pattern, flags)
            except re.error as e:
                return ToolResult.fail(f"Invalid regex pattern: {e}")

            # Find files to search
            if search_root.is_file():
                files = [search_root]
            else:
                if file_pattern:
                    files = list(search_root.glob(f"**/{file_pattern}"))
                else:
                    files = list(search_root.glob("**/*"))

            # Filter to searchable files
            searchable_files = []
            for f in files:
                if not f.is_file():
                    continue
                # Skip hidden directories
                if any(part.startswith('.') and part not in {'.env', '.gitignore', '.dockerignore'}
                       for part in f.parts):
                    if '.opencode' not in str(f):  # Allow .opencode
                        continue
                # Check extension or name
                if f.suffix.lower() in self.SEARCHABLE_EXTENSIONS or f.name in self.SEARCHABLE_NAMES:
                    searchable_files.append(f)

            # Search files based on mode
            if multiline:
                return self._search_multiline(
                    searchable_files, regex, search_root, max_results, output_mode
                )
            else:
                return self._search_lines(
                    searchable_files, regex, search_root, max_results,
                    output_mode, context_before, context_after
                )

        except Exception as e:
            return ToolResult.fail(str(e))

    def _search_lines(
        self,
        files: list,
        regex: re.Pattern,
        search_root: Path,
        max_results: int,
        output_mode: str,
        context_before: int,
        context_after: int,
    ) -> ToolResult:
        """Search files line by line."""
        results = []
        total_matches = 0
        total_files = 0

        for file_path in files:
            if output_mode == "files_with_matches" and total_files >= max_results:
                break
            if output_mode != "files_with_matches" and total_matches >= max_results:
                break

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                lines = content.splitlines()

                file_matches = []
                match_count = 0

                for line_num, line in enumerate(lines, 1):
                    if regex.search(line):
                        match_count += 1
                        total_matches += 1

                        if output_mode == "content":
                            # Collect context lines
                            context_lines = []

                            # Lines before
                            for i in range(max(0, line_num - 1 - context_before), line_num - 1):
                                context_lines.append((i + 1, lines[i], False))

                            # The matching line
                            context_lines.append((line_num, line, True))

                            # Lines after
                            for i in range(line_num, min(len(lines), line_num + context_after)):
                                context_lines.append((i + 1, lines[i], False))

                            file_matches.append(context_lines)

                        if output_mode != "files_with_matches" and total_matches >= max_results:
                            break

                if match_count > 0:
                    total_files += 1
                    try:
                        rel_path = file_path.relative_to(search_root)
                    except ValueError:
                        rel_path = file_path

                    results.append({
                        "path": rel_path,
                        "matches": file_matches,
                        "count": match_count,
                    })

            except Exception:
                continue  # Skip files that can't be read

        # Format output based on mode
        return self._format_output(
            results, regex.pattern, output_mode, total_matches, total_files, max_results
        )

    def _search_multiline(
        self,
        files: list,
        regex: re.Pattern,
        search_root: Path,
        max_results: int,
        output_mode: str,
    ) -> ToolResult:
        """Search files with multiline patterns."""
        results = []
        total_matches = 0
        total_files = 0

        for file_path in files:
            if output_mode == "files_with_matches" and total_files >= max_results:
                break
            if output_mode != "files_with_matches" and total_matches >= max_results:
                break

            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                matches = list(regex.finditer(content))

                if matches:
                    total_files += 1
                    match_count = len(matches)
                    total_matches += match_count

                    try:
                        rel_path = file_path.relative_to(search_root)
                    except ValueError:
                        rel_path = file_path

                    file_matches = []
                    if output_mode == "content":
                        lines = content.splitlines()
                        for match in matches[:max_results - total_matches + match_count]:
                            # Find line number of match start
                            start_line = content[:match.start()].count('\n') + 1
                            end_line = content[:match.end()].count('\n') + 1

                            # Get the matched text (truncated if too long)
                            matched_text = match.group(0)
                            if len(matched_text) > 200:
                                matched_text = matched_text[:200] + "..."

                            file_matches.append({
                                "start_line": start_line,
                                "end_line": end_line,
                                "text": matched_text,
                            })

                    results.append({
                        "path": rel_path,
                        "matches": file_matches,
                        "count": match_count,
                    })

            except Exception:
                continue

        return self._format_multiline_output(
            results, regex.pattern, output_mode, total_matches, total_files, max_results
        )

    def _format_output(
        self,
        results: list,
        pattern: str,
        output_mode: str,
        total_matches: int,
        total_files: int,
        max_results: int,
    ) -> ToolResult:
        """Format search results based on output mode."""
        if not results:
            return ToolResult.ok(f"No matches found for '{pattern}'")

        output_lines = []

        if output_mode == "files_with_matches":
            output_lines.append(blue(f"Found {total_files} file(s) matching '{pattern}':") + "\n")
            for result in results:
                output_lines.append(f"  {result['path']}")

        elif output_mode == "count":
            output_lines.append(blue(f"Match counts for '{pattern}':") + "\n")
            for result in results:
                output_lines.append(f"  {bold(str(result['path']))}: {result['count']} match(es)")
            output_lines.append("\n" + blue(f"Total: {total_matches} match(es) in {total_files} file(s)"))

        else:  # content mode
            output_lines.append(blue(f"Found matches for '{pattern}':") + "\n")

            for result in results:
                output_lines.append(bold(str(result['path'])))

                shown_lines = set()  # Avoid duplicate context lines
                for match_context in result["matches"]:
                    for line_num, line, is_match in match_context:
                        if line_num in shown_lines:
                            continue
                        shown_lines.add(line_num)

                        # Truncate long lines
                        display_line = line[:100] + "..." if len(line) > 100 else line

                        if is_match:
                            output_lines.append(f"  {yellow(str(line_num) + ':')} {display_line}")
                        else:
                            output_lines.append(f"  {dim(str(line_num) + ':')} {dim(display_line)}")

                output_lines.append("")  # Empty line between files

        if total_matches >= max_results:
            output_lines.append(dim(f"... (showing first {max_results} matches)"))

        output = "\n".join(output_lines)
        return ToolResult.ok(output)

    def _format_multiline_output(
        self,
        results: list,
        pattern: str,
        output_mode: str,
        total_matches: int,
        total_files: int,
        max_results: int,
    ) -> ToolResult:
        """Format multiline search results."""
        if not results:
            return ToolResult.ok(f"No matches found for '{pattern}'")

        output_lines = []

        if output_mode == "files_with_matches":
            output_lines.append(blue(f"Found {total_files} file(s) matching '{pattern}':") + "\n")
            for result in results:
                output_lines.append(f"  {result['path']}")

        elif output_mode == "count":
            output_lines.append(blue(f"Match counts for '{pattern}':") + "\n")
            for result in results:
                output_lines.append(f"  {bold(str(result['path']))}: {result['count']} match(es)")
            output_lines.append("\n" + blue(f"Total: {total_matches} match(es) in {total_files} file(s)"))

        else:  # content mode
            output_lines.append(blue(f"Found multiline matches for '{pattern}':") + "\n")

            for result in results:
                output_lines.append(bold(str(result['path'])))

                for match in result["matches"]:
                    if match["start_line"] == match["end_line"]:
                        output_lines.append(f"  {yellow('Line ' + str(match['start_line']) + ':')}")
                    else:
                        output_lines.append(f"  {yellow('Lines ' + str(match['start_line']) + '-' + str(match['end_line']) + ':')}")

                    # Indent matched text
                    for line in match["text"].splitlines():
                        output_lines.append(f"    {line[:100]}")

                output_lines.append("")

        if total_matches >= max_results:
            output_lines.append(dim(f"... (showing first {max_results} matches)"))

        output = "\n".join(output_lines)
        return ToolResult.ok(output)

    def get_schema(self) -> dict:
        """Return JSON schema for LLM function calling."""
        return {
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for (e.g., 'def login', 'class.*User', 'import react')"
                },
                "path": {
                    "type": "string",
                    "description": "Optional directory or file to search in (defaults to workspace root)"
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Optional glob pattern to filter files (e.g., '*.py', '*.ts')"
                },
                "ignore_case": {
                    "type": "boolean",
                    "description": "Whether to ignore case when matching (default: false)"
                },
                "output_mode": {
                    "type": "string",
                    "enum": ["content", "files_with_matches", "count"],
                    "description": "Output format: 'content' shows matching lines (default), 'files_with_matches' shows only file paths, 'count' shows match counts per file"
                },
                "context_before": {
                    "type": "integer",
                    "description": "Number of lines to show before each match (like grep -B)"
                },
                "context_after": {
                    "type": "integer",
                    "description": "Number of lines to show after each match (like grep -A)"
                },
                "context": {
                    "type": "integer",
                    "description": "Number of lines to show before AND after each match (like grep -C)"
                },
                "multiline": {
                    "type": "boolean",
                    "description": "Enable multiline matching - pattern can span multiple lines (default: false)"
                }
            },
            "required": ["pattern"]
        }

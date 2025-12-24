"""Tests for the tools module."""

import pytest
from pathlib import Path
from unittest.mock import Mock

from opencode.tools.base import Tool, ToolResult
from opencode.tools.read import ReadTool
from opencode.tools.write import WriteTool, generate_unified_diff
from opencode.tools.edit import EditTool
from opencode.tools.glob import GlobTool
from opencode.tools.grep import GrepTool
from opencode.mode import ModeManager, Mode


# ============================================================================
# ToolResult Tests
# ============================================================================

class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_ok_result(self):
        """Test creating a successful result."""
        result = ToolResult.ok("Success output")

        assert result.success is True
        assert result.output == "Success output"
        assert result.error == ""

    def test_fail_result(self):
        """Test creating a failed result."""
        result = ToolResult.fail("Error message", "Partial output")

        assert result.success is False
        assert result.error == "Error message"
        assert result.output == "Partial output"

    def test_llm_output_default(self):
        """Test llm_output defaults to output."""
        result = ToolResult.ok("Test output")

        assert result.llm_output == "Test output"

    def test_llm_output_custom(self):
        """Test custom llm_output."""
        result = ToolResult(
            success=True,
            output="Display output",
            _llm_output="Full LLM output"
        )

        assert result.output == "Display output"
        assert result.llm_output == "Full LLM output"


# ============================================================================
# ReadTool Tests
# ============================================================================

class TestReadTool:
    """Tests for ReadTool."""

    def test_read_existing_file(self, sample_file, temp_workspace, capsys):
        """Test reading an existing file."""
        tool = ReadTool(workspace=temp_workspace)
        result = tool.execute(path=str(sample_file))

        assert result.success is True
        assert "def hello():" in result.llm_output

    def test_read_nonexistent_file(self, temp_workspace):
        """Test reading a file that doesn't exist."""
        tool = ReadTool(workspace=temp_workspace)
        result = tool.execute(path="nonexistent.py")

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_read_with_line_range(self, sample_file, temp_workspace, capsys):
        """Test reading specific line range."""
        tool = ReadTool(workspace=temp_workspace)
        result = tool.execute(path=str(sample_file), lines="1-3")

        assert result.success is True
        # Should only have lines 1-3
        lines = result.llm_output.strip().split("\n")
        assert len(lines) == 3

    def test_read_single_line(self, sample_file, temp_workspace, capsys):
        """Test reading a single line."""
        tool = ReadTool(workspace=temp_workspace)
        result = tool.execute(path=str(sample_file), lines="1")

        assert result.success is True
        lines = result.llm_output.strip().split("\n")
        assert len(lines) == 1

    def test_read_large_file_preview(self, large_file, temp_workspace, capsys):
        """Test that large files get preview treatment."""
        tool = ReadTool(workspace=temp_workspace)
        result = tool.execute(path=str(large_file))

        assert result.success is True
        assert "LARGE FILE" in result.llm_output
        assert "PREVIEW" in result.llm_output

    def test_read_large_file_full(self, large_file, temp_workspace, capsys):
        """Test reading entire large file with full=True."""
        tool = ReadTool(workspace=temp_workspace)
        result = tool.execute(path=str(large_file), full=True)

        assert result.success is True
        # Should have all lines
        assert "600" in result.llm_output or len(result.llm_output.split("\n")) > 500

    def test_read_directory_fails(self, temp_dir, temp_workspace):
        """Test that reading a directory fails."""
        tool = ReadTool(workspace=temp_workspace)
        result = tool.execute(path=str(temp_dir))

        assert result.success is False
        assert "not a file" in result.error.lower()

    def test_get_schema(self):
        """Test tool schema generation."""
        tool = ReadTool()
        schema = tool.get_schema()

        assert "properties" in schema
        assert "path" in schema["properties"]
        assert "required" in schema
        assert "path" in schema["required"]


# ============================================================================
# WriteTool Tests
# ============================================================================

class TestWriteTool:
    """Tests for WriteTool."""

    def test_write_new_file(self, temp_workspace, capsys):
        """Test writing a new file."""
        mode_manager = ModeManager(initial_mode=Mode.BUILD)
        tool = WriteTool(mode_manager=mode_manager, workspace=temp_workspace)

        new_file = temp_workspace.root / "new_file.txt"
        result = tool.execute(path=str(new_file), content="Hello, World!")

        assert result.success is True
        assert new_file.exists()
        assert new_file.read_text() == "Hello, World!"

    def test_write_overwrite_file(self, sample_file, temp_workspace, capsys):
        """Test overwriting an existing file."""
        mode_manager = ModeManager(initial_mode=Mode.BUILD)
        tool = WriteTool(mode_manager=mode_manager, workspace=temp_workspace)

        result = tool.execute(path=str(sample_file), content="New content")

        assert result.success is True
        assert sample_file.read_text() == "New content"

    def test_write_creates_parent_dirs(self, temp_workspace, capsys):
        """Test that write creates parent directories."""
        mode_manager = ModeManager(initial_mode=Mode.BUILD)
        tool = WriteTool(mode_manager=mode_manager, workspace=temp_workspace)

        deep_file = temp_workspace.root / "deep" / "nested" / "file.txt"
        result = tool.execute(path=str(deep_file), content="Deep content")

        assert result.success is True
        assert deep_file.exists()

    def test_write_requires_build_mode(self, temp_workspace):
        """Test that write fails in PLAN mode."""
        mode_manager = ModeManager(initial_mode=Mode.PLAN)
        tool = WriteTool(mode_manager=mode_manager, workspace=temp_workspace)

        with pytest.raises(PermissionError):
            tool.execute(path="test.txt", content="content")

    def test_get_schema(self):
        """Test tool schema generation."""
        tool = WriteTool()
        schema = tool.get_schema()

        assert "properties" in schema
        assert "path" in schema["properties"]
        assert "content" in schema["properties"]
        assert "required" in schema


class TestGenerateUnifiedDiff:
    """Tests for generate_unified_diff function."""

    def test_diff_with_changes(self):
        """Test diff generation with actual changes."""
        old = "line1\nline2\nline3"
        new = "line1\nmodified\nline3"

        diff = generate_unified_diff(old, new, "test.txt")

        assert "test.txt" in diff
        assert "line2" in diff
        assert "modified" in diff

    def test_diff_no_changes(self):
        """Test diff generation with no changes."""
        content = "same content"
        diff = generate_unified_diff(content, content, "test.txt")

        # Empty diff when no changes
        assert diff == "" or "@@" not in diff


# ============================================================================
# EditTool Tests
# ============================================================================

class TestEditTool:
    """Tests for EditTool."""

    def test_edit_replaces_string(self, sample_file, temp_workspace, capsys):
        """Test basic string replacement."""
        mode_manager = ModeManager(initial_mode=Mode.BUILD)
        tool = EditTool(mode_manager=mode_manager, workspace=temp_workspace)

        result = tool.execute(
            path=str(sample_file),
            old_string="Hello, World!",
            new_string="Hello, Universe!"
        )

        assert result.success is True
        content = sample_file.read_text()
        assert "Hello, Universe!" in content
        assert "Hello, World!" not in content

    def test_edit_string_not_found(self, sample_file, temp_workspace):
        """Test editing with non-existent string."""
        mode_manager = ModeManager(initial_mode=Mode.BUILD)
        tool = EditTool(mode_manager=mode_manager, workspace=temp_workspace)

        result = tool.execute(
            path=str(sample_file),
            old_string="this does not exist",
            new_string="replacement"
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_edit_ambiguous_string(self, temp_dir, temp_workspace):
        """Test editing with non-unique string."""
        mode_manager = ModeManager(initial_mode=Mode.BUILD)
        tool = EditTool(mode_manager=mode_manager, workspace=temp_workspace)

        # Create file with duplicate content
        file_path = temp_dir / "duplicate.py"
        file_path.write_text("hello\nhello\nhello")

        result = tool.execute(
            path=str(file_path),
            old_string="hello",
            new_string="world"
        )

        assert result.success is False
        assert "ambiguous" in result.error.lower()

    def test_edit_nonexistent_file(self, temp_workspace):
        """Test editing non-existent file."""
        mode_manager = ModeManager(initial_mode=Mode.BUILD)
        tool = EditTool(mode_manager=mode_manager, workspace=temp_workspace)

        result = tool.execute(
            path="nonexistent.py",
            old_string="old",
            new_string="new"
        )

        assert result.success is False
        assert "not found" in result.error.lower()

    def test_edit_requires_build_mode(self, sample_file, temp_workspace):
        """Test that edit fails in PLAN mode."""
        mode_manager = ModeManager(initial_mode=Mode.PLAN)
        tool = EditTool(mode_manager=mode_manager, workspace=temp_workspace)

        with pytest.raises(PermissionError):
            tool.execute(
                path=str(sample_file),
                old_string="hello",
                new_string="world"
            )

    def test_get_schema(self):
        """Test tool schema generation."""
        tool = EditTool()
        schema = tool.get_schema()

        assert "properties" in schema
        assert "path" in schema["properties"]
        assert "old_string" in schema["properties"]
        assert "new_string" in schema["properties"]


# ============================================================================
# GlobTool Tests
# ============================================================================

class TestGlobTool:
    """Tests for GlobTool."""

    def test_glob_finds_files(self, temp_workspace):
        """Test finding files with glob pattern."""
        # Create some test files
        (temp_workspace.root / "file1.py").write_text("# Python file 1")
        (temp_workspace.root / "file2.py").write_text("# Python file 2")
        (temp_workspace.root / "file.txt").write_text("Text file")

        tool = GlobTool(workspace=temp_workspace)
        result = tool.execute(pattern="*.py")

        assert result.success is True
        assert "file1.py" in result.output
        assert "file2.py" in result.output
        assert "file.txt" not in result.output

    def test_glob_recursive(self, temp_workspace):
        """Test recursive glob pattern."""
        # Create nested structure
        subdir = temp_workspace.root / "subdir"
        subdir.mkdir()
        (subdir / "nested.py").write_text("# Nested")
        (temp_workspace.root / "top.py").write_text("# Top")

        tool = GlobTool(workspace=temp_workspace)
        result = tool.execute(pattern="**/*.py")

        assert result.success is True
        assert "nested.py" in result.output
        assert "top.py" in result.output

    def test_glob_no_matches(self, temp_workspace):
        """Test glob with no matches."""
        tool = GlobTool(workspace=temp_workspace)
        result = tool.execute(pattern="*.nonexistent")

        assert result.success is True
        assert "no files found" in result.output.lower()

    def test_glob_excludes_git(self, temp_workspace):
        """Test that .git directory is excluded."""
        # Create .git directory with files
        git_dir = temp_workspace.root / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("git config")
        (git_dir / "HEAD").write_text("ref: refs/heads/main")

        tool = GlobTool(workspace=temp_workspace)
        result = tool.execute(pattern="**/*")

        assert result.success is True
        # The .git directory contents should not appear in results
        # Note: .opencode/.gitignore may appear which is fine
        assert ".git/config" not in result.output
        assert ".git/HEAD" not in result.output

    def test_get_schema(self):
        """Test tool schema generation."""
        tool = GlobTool()
        schema = tool.get_schema()

        assert "properties" in schema
        assert "pattern" in schema["properties"]
        assert "required" in schema


# ============================================================================
# GrepTool Tests
# ============================================================================

class TestGrepTool:
    """Tests for GrepTool."""

    def test_grep_finds_pattern(self, temp_workspace):
        """Test finding pattern in files."""
        # Create test file
        (temp_workspace.root / "search.py").write_text(
            "def hello():\n    print('Hello World')\n"
        )

        tool = GrepTool(workspace=temp_workspace)
        result = tool.execute(pattern="hello")

        assert result.success is True
        assert "search.py" in result.output

    def test_grep_no_matches(self, temp_workspace):
        """Test grep with no matches."""
        (temp_workspace.root / "empty.py").write_text("# No matches here")

        tool = GrepTool(workspace=temp_workspace)
        result = tool.execute(pattern="nonexistent_pattern_xyz")

        assert result.success is True
        assert "no matches" in result.output.lower()

    def test_grep_ignore_case(self, temp_workspace):
        """Test case-insensitive search."""
        (temp_workspace.root / "case.py").write_text("HELLO World")

        tool = GrepTool(workspace=temp_workspace)
        result = tool.execute(pattern="hello", ignore_case=True)

        assert result.success is True
        assert "case.py" in result.output

    def test_grep_file_pattern(self, temp_workspace):
        """Test filtering by file pattern."""
        (temp_workspace.root / "match.py").write_text("target")
        (temp_workspace.root / "match.txt").write_text("target")

        tool = GrepTool(workspace=temp_workspace)
        result = tool.execute(pattern="target", file_pattern="*.py")

        assert result.success is True
        assert "match.py" in result.output
        # txt file should not be in results
        lines = result.output.split("\n")
        py_matches = [l for l in lines if "match.py" in l]
        txt_matches = [l for l in lines if "match.txt" in l]
        assert len(py_matches) >= 1
        assert len(txt_matches) == 0

    def test_grep_output_mode_files(self, temp_workspace):
        """Test files_with_matches output mode."""
        (temp_workspace.root / "a.py").write_text("pattern")
        (temp_workspace.root / "b.py").write_text("pattern")

        tool = GrepTool(workspace=temp_workspace)
        result = tool.execute(pattern="pattern", output_mode="files_with_matches")

        assert result.success is True
        assert "a.py" in result.output
        assert "b.py" in result.output

    def test_grep_output_mode_count(self, temp_workspace):
        """Test count output mode."""
        (temp_workspace.root / "multi.py").write_text("word\nword\nword")

        tool = GrepTool(workspace=temp_workspace)
        result = tool.execute(pattern="word", output_mode="count")

        assert result.success is True
        assert "3" in result.output

    def test_grep_invalid_regex(self, temp_workspace):
        """Test handling of invalid regex pattern."""
        tool = GrepTool(workspace=temp_workspace)
        result = tool.execute(pattern="[invalid(regex")

        assert result.success is False
        assert "invalid regex" in result.error.lower()

    def test_grep_context(self, temp_workspace):
        """Test context lines around matches."""
        (temp_workspace.root / "context.py").write_text(
            "line1\nline2\nMATCH\nline4\nline5"
        )

        tool = GrepTool(workspace=temp_workspace)
        result = tool.execute(pattern="MATCH", context=1)

        assert result.success is True
        assert "line2" in result.output
        assert "MATCH" in result.output
        assert "line4" in result.output

    def test_get_schema(self):
        """Test tool schema generation."""
        tool = GrepTool()
        schema = tool.get_schema()

        assert "properties" in schema
        assert "pattern" in schema["properties"]
        assert "required" in schema


# ============================================================================
# Tool Base Class Tests
# ============================================================================

class TestToolBase:
    """Tests for Tool base class functionality."""

    def test_to_anthropic_tool(self):
        """Test Anthropic tool format conversion."""
        tool = ReadTool()
        anthropic_format = tool.to_anthropic_tool()

        assert anthropic_format["name"] == "read"
        assert "description" in anthropic_format
        assert "input_schema" in anthropic_format
        assert anthropic_format["input_schema"]["type"] == "object"

    def test_to_openai_tool(self):
        """Test OpenAI tool format conversion."""
        tool = ReadTool()
        openai_format = tool.to_openai_tool()

        assert openai_format["type"] == "function"
        assert openai_format["function"]["name"] == "read"
        assert "parameters" in openai_format["function"]

    def test_resolve_path_relative(self, temp_workspace):
        """Test resolving relative paths."""
        tool = ReadTool(workspace=temp_workspace)
        resolved = tool._resolve_path("subdir/file.py")

        assert resolved.is_absolute()
        assert str(temp_workspace.root) in str(resolved)

    def test_resolve_path_outside_workspace(self, temp_workspace):
        """Test that paths outside workspace raise error."""
        tool = ReadTool(workspace=temp_workspace)

        with pytest.raises(ValueError):
            tool._resolve_path("/etc/passwd")

    def test_check_mode_build_required(self, temp_workspace):
        """Test mode checking for build-required tools."""
        mode_manager = ModeManager(initial_mode=Mode.PLAN)
        tool = WriteTool(mode_manager=mode_manager, workspace=temp_workspace)

        with pytest.raises(PermissionError):
            tool._check_mode()

    def test_checkpoint_called(self, temp_workspace):
        """Test that checkpoint function is called."""
        checkpoint_calls = []

        def mock_checkpoint(desc):
            checkpoint_calls.append(desc)

        mode_manager = ModeManager(initial_mode=Mode.BUILD)
        tool = WriteTool(
            mode_manager=mode_manager,
            workspace=temp_workspace,
            checkpoint_fn=mock_checkpoint
        )

        tool.execute(
            path=str(temp_workspace.root / "test.txt"),
            content="content"
        )

        assert len(checkpoint_calls) == 1
        assert "test.txt" in checkpoint_calls[0]

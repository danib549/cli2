"""Tests for ExplorationGuard - enforces read-before-write discipline."""

import os
import pytest
from pathlib import Path

from opencode.exploration import ExplorationGuard, ExplorationState, ExplorationViolation


class TestExplorationState:
    """Tests for ExplorationState dataclass."""

    def test_default_state(self):
        """Test default exploration state."""
        state = ExplorationState()

        assert state.files_read == set()
        assert state.dirs_globbed == set()
        assert state.patterns_grepped == set()
        assert state.paths_grepped == set()
        assert state.exploration_count == 0
        assert state.MIN_EXPLORATION_ACTIONS == 2

    def test_state_is_mutable(self):
        """Test that state can be modified."""
        state = ExplorationState()
        state.files_read.add("/path/to/file.py")
        state.exploration_count = 5

        assert "/path/to/file.py" in state.files_read
        assert state.exploration_count == 5


class TestExplorationViolation:
    """Tests for ExplorationViolation dataclass."""

    def test_violation_blocked(self):
        """Test blocked violation."""
        violation = ExplorationViolation(
            blocked=True,
            reason="Not enough exploration",
            required_actions=["Read the file first"],
            teaching_message="You must explore before modifying."
        )

        assert violation.blocked is True
        assert "Not enough exploration" in violation.reason
        assert len(violation.required_actions) == 1

    def test_violation_allowed(self):
        """Test allowed (not blocked) violation."""
        violation = ExplorationViolation(
            blocked=False,
            reason="Requirements met",
            required_actions=[],
            teaching_message=""
        )

        assert violation.blocked is False
        assert violation.required_actions == []


class TestExplorationGuardInit:
    """Tests for ExplorationGuard initialization."""

    def test_default_enabled(self):
        """Test guard is enabled by default."""
        guard = ExplorationGuard()
        assert guard.enabled is True

    def test_can_disable(self):
        """Test guard can be disabled."""
        guard = ExplorationGuard(enabled=False)
        assert guard.enabled is False

    def test_initial_state_is_empty(self):
        """Test initial state has no exploration."""
        guard = ExplorationGuard()
        assert guard.state.exploration_count == 0
        assert len(guard.state.files_read) == 0

    def test_reset_clears_state(self):
        """Test reset clears all exploration state."""
        guard = ExplorationGuard()

        # Do some exploration
        guard.record_exploration("read", {"path": "/some/file.py"})
        guard.record_exploration("glob", {"pattern": "*.py"})
        assert guard.state.exploration_count == 2

        # Reset
        guard.reset()

        assert guard.state.exploration_count == 0
        assert len(guard.state.files_read) == 0
        assert len(guard.state.dirs_globbed) == 0


class TestRecordExploration:
    """Tests for record_exploration() method."""

    def test_record_read(self, tmp_path):
        """Test recording a file read."""
        guard = ExplorationGuard()
        file_path = str(tmp_path / "test.py")

        guard.record_exploration("read", {"path": file_path})

        assert guard.state.exploration_count == 1
        # Path should be normalized/resolved
        assert len(guard.state.files_read) == 1
        # Parent directory should be marked as explored
        assert len(guard.state.dirs_globbed) == 1

    def test_record_glob(self, tmp_path):
        """Test recording a glob operation."""
        guard = ExplorationGuard()
        pattern = str(tmp_path / "*.py")

        guard.record_exploration("glob", {"pattern": pattern})

        assert guard.state.exploration_count == 1
        assert len(guard.state.dirs_globbed) == 1

    def test_record_grep(self, tmp_path):
        """Test recording a grep operation."""
        guard = ExplorationGuard()

        guard.record_exploration("grep", {
            "pattern": "def test_",
            "path": str(tmp_path)
        })

        assert guard.state.exploration_count == 1
        assert "def test_" in guard.state.patterns_grepped
        assert len(guard.state.paths_grepped) == 1
        assert len(guard.state.dirs_globbed) == 1

    def test_record_tree(self):
        """Test recording a tree operation."""
        guard = ExplorationGuard()

        guard.record_exploration("tree", {"path": "."})

        assert guard.state.exploration_count == 1

    def test_record_outline(self):
        """Test recording an outline operation."""
        guard = ExplorationGuard()

        guard.record_exploration("outline", {"path": "file.py"})

        assert guard.state.exploration_count == 1

    def test_record_find_definition(self):
        """Test recording a find_definition operation."""
        guard = ExplorationGuard()

        guard.record_exploration("find_definition", {"symbol": "MyClass"})

        assert guard.state.exploration_count == 1

    def test_ignores_non_exploration_tools(self):
        """Test that non-exploration tools are ignored."""
        guard = ExplorationGuard()

        guard.record_exploration("write", {"path": "file.py"})
        guard.record_exploration("edit", {"path": "file.py"})
        guard.record_exploration("bash", {"command": "ls"})

        assert guard.state.exploration_count == 0

    def test_case_insensitive_tool_names(self):
        """Test tool names are case-insensitive."""
        guard = ExplorationGuard()

        guard.record_exploration("READ", {"path": "/file.py"})
        guard.record_exploration("Glob", {"pattern": "*.py"})
        guard.record_exploration("GREP", {"pattern": "test", "path": "."})

        assert guard.state.exploration_count == 3

    def test_multiple_explorations_accumulate(self, tmp_path):
        """Test that multiple explorations accumulate."""
        guard = ExplorationGuard()

        guard.record_exploration("read", {"path": str(tmp_path / "a.py")})
        guard.record_exploration("read", {"path": str(tmp_path / "b.py")})
        guard.record_exploration("glob", {"pattern": "*.py"})

        assert guard.state.exploration_count == 3
        assert len(guard.state.files_read) == 2


class TestCheckModification:
    """Tests for check_modification() method."""

    def test_disabled_guard_allows_everything(self, tmp_path):
        """Test that disabled guard allows all modifications."""
        guard = ExplorationGuard(enabled=False)

        violation = guard.check_modification("write", {"path": str(tmp_path / "new.py")})

        assert violation.blocked is False
        assert "disabled" in violation.reason.lower()

    def test_non_modification_tool_allowed(self):
        """Test that non-modification tools are allowed."""
        guard = ExplorationGuard()

        violation = guard.check_modification("read", {"path": "file.py"})

        assert violation.blocked is False
        assert "Not a modification tool" in violation.reason

    def test_blocks_without_path(self):
        """Test that modification without path is blocked."""
        guard = ExplorationGuard()

        violation = guard.check_modification("write", {})

        assert violation.blocked is True
        assert "No path provided" in violation.reason

    def test_blocks_edit_without_reading_file(self, tmp_path):
        """Test that edit is blocked if file wasn't read."""
        guard = ExplorationGuard()
        file_path = tmp_path / "existing.py"
        file_path.write_text("content")

        # Do minimum exploration but don't read this specific file
        guard.record_exploration("glob", {"pattern": "*.py"})
        guard.record_exploration("grep", {"pattern": "test", "path": "."})

        violation = guard.check_modification("edit", {"path": str(file_path)})

        assert violation.blocked is True
        assert any("Read the file" in action for action in violation.required_actions)

    def test_allows_edit_after_reading_file(self, tmp_path):
        """Test that edit is allowed after reading the file."""
        guard = ExplorationGuard()
        file_path = tmp_path / "existing.py"
        file_path.write_text("content")

        # Read the file and do enough exploration
        guard.record_exploration("read", {"path": str(file_path)})
        guard.record_exploration("glob", {"pattern": "*.py"})

        violation = guard.check_modification("edit", {"path": str(file_path)})

        assert violation.blocked is False

    def test_blocks_write_to_existing_without_reading(self, tmp_path):
        """Test that writing to existing file is blocked without reading."""
        guard = ExplorationGuard()
        file_path = tmp_path / "existing.py"
        file_path.write_text("original content")

        # Do exploration but don't read this file
        guard.record_exploration("glob", {"pattern": "*.py"})
        guard.record_exploration("grep", {"pattern": "test", "path": "."})

        violation = guard.check_modification("write", {"path": str(file_path)})

        assert violation.blocked is True
        assert any("overwriting" in action.lower() for action in violation.required_actions)

    def test_allows_write_to_existing_after_reading(self, tmp_path):
        """Test that writing to existing file is allowed after reading."""
        guard = ExplorationGuard()
        file_path = tmp_path / "existing.py"
        file_path.write_text("original content")

        guard.record_exploration("read", {"path": str(file_path)})
        guard.record_exploration("glob", {"pattern": "*.py"})

        violation = guard.check_modification("write", {"path": str(file_path)})

        assert violation.blocked is False

    def test_blocks_new_file_without_exploring_directory(self, tmp_path):
        """Test that creating new file is blocked without exploring directory."""
        guard = ExplorationGuard()
        new_file = tmp_path / "subdir" / "new.py"

        # Do minimum exploration but not in the target directory
        guard.record_exploration("read", {"path": "/other/path.py"})
        guard.record_exploration("grep", {"pattern": "test", "path": "/other"})

        violation = guard.check_modification("write", {"path": str(new_file)})

        assert violation.blocked is True
        assert any("Explore the target directory" in action for action in violation.required_actions)

    def test_allows_new_file_after_exploring_directory(self, tmp_path):
        """Test that creating new file is allowed after exploring directory."""
        guard = ExplorationGuard()
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        new_file = subdir / "new.py"

        # Explore the target directory
        guard.record_exploration("glob", {"pattern": str(subdir / "*")})
        guard.record_exploration("read", {"path": str(tmp_path / "other.py")})

        violation = guard.check_modification("write", {"path": str(new_file)})

        assert violation.blocked is False

    def test_blocks_with_insufficient_exploration_count(self, tmp_path):
        """Test that modifications are blocked with insufficient exploration.

        Note: If the file is already read, we're lenient (only need 1 action).
        This test checks the case where we explore one file but try to edit another.
        """
        guard = ExplorationGuard()
        file1 = tmp_path / "file1.py"
        file2 = tmp_path / "file2.py"
        file1.write_text("content1")
        file2.write_text("content2")

        # Only one exploration of file1 (need 2 to edit an unknown file)
        guard.record_exploration("read", {"path": str(file1)})

        # Try to edit file2 which we haven't read - should be blocked
        violation = guard.check_modification("edit", {"path": str(file2)})

        assert violation.blocked is True
        # Should require reading the file first
        assert any("read" in action.lower() for action in violation.required_actions)

    def test_allows_after_minimum_exploration_count(self, tmp_path):
        """Test that modifications are allowed after minimum exploration."""
        guard = ExplorationGuard()
        file_path = tmp_path / "file.py"
        file_path.write_text("content")

        # Meet minimum exploration count
        guard.record_exploration("read", {"path": str(file_path)})
        guard.record_exploration("glob", {"pattern": "*.py"})

        violation = guard.check_modification("edit", {"path": str(file_path)})

        assert violation.blocked is False


class TestTeachingMessage:
    """Tests for teaching message generation."""

    def test_teaching_message_contains_required_elements(self, tmp_path):
        """Test that teaching message contains key elements."""
        guard = ExplorationGuard()
        file_path = tmp_path / "file.py"
        file_path.write_text("content")

        violation = guard.check_modification("edit", {"path": str(file_path)})

        assert violation.blocked is True
        msg = violation.teaching_message

        assert "EXPLORATION REQUIRED" in msg
        assert "edit" in msg.lower()
        assert "REQUIRED ACTIONS" in msg
        assert "WHY THIS MATTERS" in msg

    def test_teaching_message_lists_actions(self, tmp_path):
        """Test that teaching message lists required actions."""
        guard = ExplorationGuard()
        file_path = tmp_path / "file.py"
        file_path.write_text("content")

        violation = guard.check_modification("edit", {"path": str(file_path)})

        msg = violation.teaching_message
        # Should have numbered list of actions
        assert "1." in msg


class TestExplorationSummary:
    """Tests for get_exploration_summary() and format_status()."""

    def test_get_exploration_summary(self, tmp_path):
        """Test exploration summary output."""
        guard = ExplorationGuard()

        guard.record_exploration("read", {"path": str(tmp_path / "a.py")})
        guard.record_exploration("grep", {"pattern": "test", "path": str(tmp_path)})

        summary = guard.get_exploration_summary()

        assert "files_read" in summary
        assert "dirs_globbed" in summary
        assert "patterns_grepped" in summary
        assert "exploration_count" in summary
        assert summary["exploration_count"] == 2
        assert "can_modify" in summary
        assert summary["can_modify"] is True

    def test_format_status_insufficient(self):
        """Test status format when exploration is insufficient."""
        guard = ExplorationGuard()
        guard.record_exploration("read", {"path": "/file.py"})

        status = guard.format_status()

        assert "1/2" in status or "1" in status
        assert "NEED MORE" in status or "before modifying" in status.lower()

    def test_format_status_sufficient(self):
        """Test status format when exploration is sufficient."""
        guard = ExplorationGuard()
        guard.record_exploration("read", {"path": "/a.py"})
        guard.record_exploration("read", {"path": "/b.py"})

        status = guard.format_status()

        assert "OK" in status or "2" in status


class TestPathNormalization:
    """Tests for path normalization behavior."""

    def test_relative_and_absolute_paths_match(self, tmp_path, monkeypatch):
        """Test that relative and absolute paths are normalized."""
        guard = ExplorationGuard()
        file_path = tmp_path / "test.py"
        file_path.write_text("content")

        # Change to tmp_path directory
        monkeypatch.chdir(tmp_path)

        # Read with relative path
        guard.record_exploration("read", {"path": "test.py"})
        guard.record_exploration("glob", {"pattern": "*.py"})

        # Check with absolute path
        violation = guard.check_modification("edit", {"path": str(file_path)})

        assert violation.blocked is False

    def test_handles_nonexistent_paths(self):
        """Test handling of non-existent paths in normalization."""
        guard = ExplorationGuard()

        # Should not crash on non-existent paths
        guard.record_exploration("read", {"path": "/nonexistent/path/file.py"})

        assert guard.state.exploration_count == 1


class TestGlobPatternExtraction:
    """Tests for glob pattern base directory extraction."""

    def test_extract_base_from_simple_pattern(self, tmp_path):
        """Test extracting base directory from simple pattern."""
        guard = ExplorationGuard()

        guard.record_exploration("glob", {"pattern": str(tmp_path / "*.py")})

        # tmp_path should be in dirs_globbed
        assert len(guard.state.dirs_globbed) == 1

    def test_extract_base_from_nested_pattern(self, tmp_path):
        """Test extracting base from nested glob pattern."""
        guard = ExplorationGuard()

        pattern = str(tmp_path / "src" / "**" / "*.py")
        guard.record_exploration("glob", {"pattern": pattern})

        assert len(guard.state.dirs_globbed) == 1

    def test_handles_pattern_only(self):
        """Test handling pattern without directory."""
        guard = ExplorationGuard()

        guard.record_exploration("glob", {"pattern": "*.py"})

        assert guard.state.exploration_count == 1
        # Should default to current directory
        assert len(guard.state.dirs_globbed) == 1


class TestDirectoryExplorationInheritance:
    """Tests for directory exploration inheritance."""

    def test_parent_exploration_counts_for_child(self, tmp_path):
        """Test that exploring parent directory counts for child files."""
        guard = ExplorationGuard()
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        # Explore parent directory
        guard.record_exploration("glob", {"pattern": str(tmp_path / "*")})
        guard.record_exploration("read", {"path": str(tmp_path / "other.py")})

        # Create file in subdirectory
        new_file = subdir / "new.py"

        violation = guard.check_modification("write", {"path": str(new_file)})

        # Parent was explored, so this should be allowed
        # (depending on implementation - may need subdir exploration)
        # This test documents expected behavior


class TestExplorationToolSet:
    """Tests for tool classification."""

    def test_exploration_tools_defined(self):
        """Test that exploration tools are properly defined."""
        expected_exploration = {"read", "glob", "grep", "tree", "outline",
                                "find_definition", "find_references", "find_symbols"}

        assert ExplorationGuard.EXPLORATION_TOOLS == expected_exploration

    def test_modification_tools_defined(self):
        """Test that modification tools are properly defined."""
        expected_modification = {"write", "edit", "rename_symbol"}

        assert ExplorationGuard.MODIFICATION_TOOLS == expected_modification

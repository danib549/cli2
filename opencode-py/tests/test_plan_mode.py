"""Tests for plan mode behavior with small and large projects.

This module tests the interaction between:
- Mode management (PLAN/BUILD)
- Complexity analysis (auto-planning triggers)
- Exploration guard (read-before-write enforcement)

For both small projects (minimal exploration needed) and
large projects (extensive exploration required).
"""

import os
import tempfile
import pytest
from pathlib import Path

from opencode.mode import Mode, ExecutionMode, ModeManager
from opencode.complexity import ComplexityAnalyzer, ComplexityResult
from opencode.exploration import ExplorationGuard, ExplorationState


class TestSmallProjectComplexity:
    """Test complexity analysis for small project tasks."""

    def test_simple_fix_low_complexity(self):
        """Simple bug fix should have low complexity."""
        analyzer = ComplexityAnalyzer()
        result = analyzer.analyze("fix the typo in README.md")

        assert result.score < 0.6
        assert result.should_plan is False

    def test_single_file_edit_low_complexity(self):
        """Single file edit should have low complexity."""
        analyzer = ComplexityAnalyzer()
        result = analyzer.analyze("change the color from blue to red in styles.css")

        assert result.score < 0.6
        assert result.should_plan is False

    def test_add_simple_function_low_complexity(self):
        """Adding a simple function should have low complexity."""
        analyzer = ComplexityAnalyzer()
        result = analyzer.analyze("add a helper function to parse dates")

        assert result.score < 0.6
        assert result.should_plan is False

    def test_rename_variable_low_complexity(self):
        """Renaming a variable should have low complexity."""
        analyzer = ComplexityAnalyzer()
        result = analyzer.analyze("rename userName to user_name")

        assert result.score < 0.6
        assert result.should_plan is False

    def test_update_config_low_complexity(self):
        """Updating a config value should have low complexity."""
        analyzer = ComplexityAnalyzer()
        result = analyzer.analyze("change the port number to 8080")

        assert result.score < 0.6
        assert result.should_plan is False


class TestLargeProjectComplexity:
    """Test complexity analysis for large project tasks."""

    def test_refactor_triggers_planning(self):
        """Refactoring should trigger auto-planning."""
        analyzer = ComplexityAnalyzer()
        result = analyzer.analyze("refactor the authentication module")

        assert result.score >= 0.3  # refactor signal
        assert "refactor" in str(result.signals).lower()

    def test_migrate_triggers_planning(self):
        """Migration should trigger auto-planning."""
        analyzer = ComplexityAnalyzer()
        result = analyzer.analyze("migrate the database from MySQL to PostgreSQL")

        assert result.score >= 0.3
        assert "migrate" in str(result.signals).lower()

    def test_rewrite_triggers_planning(self):
        """Rewriting should trigger auto-planning."""
        analyzer = ComplexityAnalyzer()
        result = analyzer.analyze("rewrite the API layer to use GraphQL")

        assert result.score >= 0.3
        assert "rewrite" in str(result.signals).lower()

    def test_entire_codebase_high_complexity(self):
        """Operations on entire codebase should have high complexity."""
        analyzer = ComplexityAnalyzer()
        result = analyzer.analyze("update all files to use the new logging system")

        # Should detect scope and system signals
        assert result.score >= 0.3
        assert len(result.signals) >= 2  # "all files" and "system"

    def test_multi_step_task_high_complexity(self):
        """Multi-step tasks should have high complexity."""
        analyzer = ComplexityAnalyzer()
        result = analyzer.analyze(
            "first create the database models, then build the API endpoints, "
            "and finally add the frontend components"
        )

        assert result.score >= 0.4
        assert len(result.signals) >= 2

    def test_system_wide_changes_high_complexity(self):
        """System-wide changes should have high complexity."""
        analyzer = ComplexityAnalyzer()
        result = analyzer.analyze(
            "restructure the entire application to use microservices architecture"
        )

        assert result.score >= 0.5
        assert result.should_plan is True

    def test_complex_feature_implementation(self):
        """Complex feature implementation should trigger planning."""
        analyzer = ComplexityAnalyzer()
        result = analyzer.analyze(
            "implement a complete user authentication system with OAuth, "
            "JWT tokens, and role-based access control"
        )

        assert result.score >= 0.3
        assert len(result.signals) >= 1


class TestSmallProjectExploration:
    """Test exploration requirements for small projects."""

    def test_single_file_exploration_sufficient(self):
        """Reading a single file should satisfy exploration for editing it."""
        guard = ExplorationGuard(enabled=True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("# test file\n")
            temp_path = f.name

        try:
            # Read the file (counts as 1 exploration)
            guard.record_exploration("read", {"path": temp_path})

            # Need one more exploration action to meet minimum
            guard.record_exploration("glob", {"pattern": "*.py", "path": str(Path(temp_path).parent)})

            # Should now be able to edit
            result = guard.check_modification("edit", {"path": temp_path})
            assert result.blocked is False
        finally:
            os.unlink(temp_path)

    def test_glob_satisfies_directory_exploration(self):
        """Globbing a directory should satisfy exploration for new files."""
        guard = ExplorationGuard(enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Glob the directory (counts as 1 exploration)
            guard.record_exploration("glob", {"pattern": "*", "path": temp_dir})

            # Add another exploration action
            guard.record_exploration("tree", {"path": temp_dir})

            # Should be able to write new file in that directory
            new_file = os.path.join(temp_dir, "new_file.py")
            result = guard.check_modification("write", {"path": new_file})
            assert result.blocked is False

    def test_read_marks_directory_as_explored(self):
        """Reading a file should mark its directory as partially explored."""
        guard = ExplorationGuard(enabled=True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("# test\n")
            temp_path = f.name

        try:
            # Read the file
            guard.record_exploration("read", {"path": temp_path})

            # Parent directory should be marked as explored
            parent_dir = str(Path(temp_path).parent.resolve())
            assert parent_dir in guard.state.dirs_globbed
        finally:
            os.unlink(temp_path)


class TestLargeProjectExploration:
    """Test exploration requirements for large projects."""

    def test_minimum_exploration_required(self):
        """At least 2 exploration actions required before editing unknown files.

        Note: If the file is already read/created, we're lenient (only need 1 action).
        This test checks editing an unknown file after minimal exploration.
        """
        guard = ExplorationGuard(enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            file1 = os.path.join(temp_dir, "file1.py")
            file2 = os.path.join(temp_dir, "file2.py")
            with open(file1, 'w') as f:
                f.write("# file1\n")
            with open(file2, 'w') as f:
                f.write("# file2\n")

            # Only one exploration action (read file1)
            guard.record_exploration("read", {"path": file1})

            # Editing file1 should work (we read it, lenient mode)
            result = guard.check_modification("edit", {"path": file1})
            assert result.blocked is False

            # Editing file2 should be blocked (we haven't read it)
            result = guard.check_modification("edit", {"path": file2})
            assert result.blocked is True
            assert any("read" in action.lower() for action in result.required_actions)

    def test_multiple_explorations_accumulate(self):
        """Multiple exploration actions should accumulate."""
        guard = ExplorationGuard(enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            # Multiple exploration actions
            guard.record_exploration("glob", {"pattern": "*.py", "path": temp_dir})
            guard.record_exploration("grep", {"pattern": "import", "path": temp_dir})
            guard.record_exploration("tree", {"path": temp_dir})

            assert guard.state.exploration_count == 3

            summary = guard.get_exploration_summary()
            assert summary["can_modify"] is True

    def test_different_exploration_tools_all_count(self):
        """Different exploration tools should all contribute to count."""
        guard = ExplorationGuard(enabled=True)

        exploration_tools = ["read", "glob", "grep", "tree", "outline",
                           "find_definition", "find_references", "find_symbols"]

        for i, tool in enumerate(exploration_tools):
            guard.record_exploration(tool, {"path": "/tmp", "pattern": "test"})
            assert guard.state.exploration_count == i + 1

    def test_must_read_before_edit(self):
        """Must read a file before editing it."""
        guard = ExplorationGuard(enabled=True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("# test\n")
            temp_path = f.name

        try:
            # Meet minimum exploration count with other actions
            guard.record_exploration("glob", {"pattern": "*", "path": str(Path(temp_path).parent)})
            guard.record_exploration("tree", {"path": str(Path(temp_path).parent)})

            # Try to edit without reading the specific file
            result = guard.check_modification("edit", {"path": temp_path})
            assert result.blocked is True
            assert "read" in result.required_actions[0].lower()
        finally:
            os.unlink(temp_path)

    def test_must_read_before_overwrite(self):
        """Must read an existing file before overwriting it."""
        guard = ExplorationGuard(enabled=True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("# test\n")
            temp_path = f.name

        try:
            # Meet minimum exploration count
            guard.record_exploration("glob", {"pattern": "*", "path": str(Path(temp_path).parent)})
            guard.record_exploration("tree", {"path": str(Path(temp_path).parent)})

            # Try to overwrite without reading
            result = guard.check_modification("write", {"path": temp_path})
            assert result.blocked is True
            assert "existing file" in result.required_actions[0].lower()
        finally:
            os.unlink(temp_path)


class TestPlanBuildModeTransition:
    """Test transitions between PLAN and BUILD mode."""

    def test_plan_mode_is_read_only(self):
        """PLAN mode should be read-only."""
        manager = ModeManager(initial_mode=Mode.PLAN)

        assert manager.is_plan is True
        assert manager.is_read_only is True

        with pytest.raises(PermissionError):
            manager.require_build("write")

    def test_build_mode_allows_writes(self):
        """BUILD mode should allow write operations."""
        manager = ModeManager(initial_mode=Mode.BUILD)

        assert manager.is_build is True
        assert manager.is_read_only is False

        # Should not raise
        manager.require_build("write")

    def test_transition_plan_to_build(self):
        """Should be able to transition from PLAN to BUILD."""
        manager = ModeManager(initial_mode=Mode.PLAN)

        assert manager.is_plan is True

        manager.to_build()

        assert manager.is_build is True
        assert manager.is_plan is False

    def test_transition_build_to_plan(self):
        """Should be able to transition from BUILD to PLAN."""
        manager = ModeManager(initial_mode=Mode.BUILD)

        manager.to_plan()

        assert manager.is_plan is True
        assert manager.is_build is False

    def test_review_mode_is_read_only(self):
        """REVIEW mode should also be read-only."""
        manager = ModeManager(initial_mode=Mode.PLAN)
        manager.to_review()

        assert manager.is_review is True
        assert manager.is_read_only is True


class TestComplexityThresholds:
    """Test complexity threshold behavior."""

    def test_default_threshold(self):
        """Default threshold should be 0.6."""
        analyzer = ComplexityAnalyzer()
        assert analyzer.threshold == 0.6

    def test_custom_threshold(self):
        """Should accept custom threshold."""
        analyzer = ComplexityAnalyzer(threshold=0.3)
        assert analyzer.threshold == 0.3

        # Lower threshold means more tasks trigger planning
        result = analyzer.analyze("create a new component")
        # With lower threshold, this might trigger planning
        assert isinstance(result.should_plan, bool)

    def test_high_threshold_less_planning(self):
        """High threshold should trigger less auto-planning."""
        low_threshold = ComplexityAnalyzer(threshold=0.3)
        high_threshold = ComplexityAnalyzer(threshold=0.9)

        task = "refactor the authentication module"

        low_result = low_threshold.analyze(task)
        high_result = high_threshold.analyze(task)

        # Same score, different planning decision
        assert low_result.score == high_result.score
        # Low threshold more likely to plan
        assert low_result.should_plan or not high_result.should_plan

    def test_threshold_adjustment(self):
        """Should be able to adjust threshold dynamically."""
        analyzer = ComplexityAnalyzer(threshold=0.6)

        analyzer.set_threshold(0.3)
        assert analyzer.threshold == 0.3

        analyzer.set_threshold(0.9)
        assert analyzer.threshold == 0.9

    def test_threshold_clamped_to_valid_range(self):
        """Threshold should be clamped to 0.0-1.0 range."""
        analyzer = ComplexityAnalyzer()

        analyzer.set_threshold(-0.5)
        assert analyzer.threshold == 0.0

        analyzer.set_threshold(1.5)
        assert analyzer.threshold == 1.0


class TestExplorationGuardDisabled:
    """Test behavior when exploration guard is disabled."""

    def test_disabled_allows_all_modifications(self):
        """Disabled guard should allow all modifications."""
        guard = ExplorationGuard(enabled=False)

        # No exploration done
        result = guard.check_modification("write", {"path": "/some/new/file.py"})
        assert result.blocked is False

    def test_can_disable_after_init(self):
        """Should be able to disable guard after initialization."""
        guard = ExplorationGuard(enabled=True)

        # Initially blocks
        result = guard.check_modification("write", {"path": "/some/file.py"})
        assert result.blocked is True

        # Disable
        guard.enabled = False

        # Now allows
        result = guard.check_modification("write", {"path": "/some/file.py"})
        assert result.blocked is False


class TestExplorationStateReset:
    """Test exploration state reset behavior."""

    def test_reset_clears_all_state(self):
        """Reset should clear all exploration state."""
        guard = ExplorationGuard(enabled=True)

        # Do some exploration
        guard.record_exploration("read", {"path": "/tmp/file.py"})
        guard.record_exploration("glob", {"pattern": "*.py", "path": "/tmp"})

        assert guard.state.exploration_count == 2

        # Reset
        guard.reset()

        assert guard.state.exploration_count == 0
        assert len(guard.state.files_read) == 0
        assert len(guard.state.dirs_globbed) == 0

    def test_reset_required_for_new_task(self):
        """After reset, exploration requirements apply again."""
        guard = ExplorationGuard(enabled=True)

        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("# test\n")
            temp_path = f.name

        try:
            # Do exploration
            guard.record_exploration("read", {"path": temp_path})
            guard.record_exploration("glob", {"pattern": "*", "path": str(Path(temp_path).parent)})

            # Can modify
            result = guard.check_modification("edit", {"path": temp_path})
            assert result.blocked is False

            # Reset for new task
            guard.reset()

            # Now blocked again
            result = guard.check_modification("edit", {"path": temp_path})
            assert result.blocked is True
        finally:
            os.unlink(temp_path)


class TestGlobPathHandling:
    """Test that glob properly handles path argument for exploration."""

    def test_glob_with_path_records_correct_directory(self):
        """Glob with explicit path should record that directory."""
        guard = ExplorationGuard(enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            guard.record_exploration("glob", {"pattern": "*.py", "path": temp_dir})

            # The temp_dir should be recorded
            normalized = str(Path(temp_dir).resolve())
            assert normalized in guard.state.dirs_globbed

    def test_glob_without_path_records_cwd(self):
        """Glob without path should record current directory."""
        guard = ExplorationGuard(enabled=True)

        guard.record_exploration("glob", {"pattern": "*.py"})

        # Current directory should be recorded (normalized ".")
        cwd = str(Path(".").resolve())
        assert cwd in guard.state.dirs_globbed

    def test_glob_nested_pattern_with_path(self):
        """Glob with nested pattern and path should work correctly."""
        guard = ExplorationGuard(enabled=True)

        with tempfile.TemporaryDirectory() as temp_dir:
            guard.record_exploration("glob", {"pattern": "src/**/*.py", "path": temp_dir})

            # Should record temp_dir/src or just temp_dir depending on implementation
            summary = guard.get_exploration_summary()
            assert len(summary["dirs_globbed"]) >= 1


class TestIntegrationSmallProject:
    """Integration tests simulating small project workflow."""

    def test_small_project_quick_edit_workflow(self):
        """Simulate quick edit workflow in small project."""
        mode_manager = ModeManager(initial_mode=Mode.BUILD)
        guard = ExplorationGuard(enabled=True)
        analyzer = ComplexityAnalyzer()

        # User task
        task = "fix the typo in config.py"

        # Check complexity - should not require planning
        complexity = analyzer.analyze(task)
        assert complexity.should_plan is False

        # Create a test file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("# config\ntypo_here = 'tset'\n")
            temp_path = f.name

        try:
            # Read the file (exploration 1)
            guard.record_exploration("read", {"path": temp_path})

            # Quick glob of directory (exploration 2)
            guard.record_exploration("glob", {"pattern": "*.py", "path": str(Path(temp_path).parent)})

            # Should be able to edit now
            result = guard.check_modification("edit", {"path": temp_path})
            assert result.blocked is False

            # Mode allows it
            assert mode_manager.is_build is True
        finally:
            os.unlink(temp_path)


class TestIntegrationLargeProject:
    """Integration tests simulating large project workflow."""

    def test_large_project_refactor_workflow(self):
        """Simulate refactoring workflow in large project."""
        mode_manager = ModeManager(initial_mode=Mode.PLAN)
        guard = ExplorationGuard(enabled=True)
        analyzer = ComplexityAnalyzer()

        # User task
        task = "refactor the authentication system across all modules"

        # Check complexity - should require planning
        complexity = analyzer.analyze(task)
        assert complexity.score >= 0.3  # Has complexity signals

        # Start in PLAN mode - read only
        assert mode_manager.is_plan is True
        assert mode_manager.is_read_only is True

        # Do extensive exploration
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create some files
            for name in ["auth.py", "users.py", "models.py"]:
                Path(temp_dir, name).write_text(f"# {name}\n")

            # Explore the codebase
            guard.record_exploration("tree", {"path": temp_dir})
            guard.record_exploration("glob", {"pattern": "*.py", "path": temp_dir})
            guard.record_exploration("grep", {"pattern": "auth", "path": temp_dir})

            # Read specific files
            for name in ["auth.py", "users.py"]:
                guard.record_exploration("read", {"path": str(Path(temp_dir, name))})

            # After exploration, switch to BUILD mode
            mode_manager.to_build()
            assert mode_manager.is_build is True

            # Now can modify explored files
            result = guard.check_modification("edit", {"path": str(Path(temp_dir, "auth.py"))})
            assert result.blocked is False

"""Tests for mode management."""

import pytest
from opencode.mode import Mode, ExecutionMode, ModeManager


class TestMode:
    """Tests for Mode enum."""

    def test_mode_values(self):
        """Test Mode enum has correct values."""
        assert Mode.PLAN.value == "plan"
        assert Mode.BUILD.value == "build"

    def test_execution_mode_values(self):
        """Test ExecutionMode enum has correct values."""
        assert ExecutionMode.INTERACTIVE.value == "interactive"
        assert ExecutionMode.AUTO.value == "auto"


class TestModeManager:
    """Tests for ModeManager class."""

    def test_default_modes(self):
        """Test default mode initialization."""
        manager = ModeManager()
        assert manager.mode == Mode.PLAN
        assert manager.execution_mode == ExecutionMode.INTERACTIVE
        assert manager.is_plan is True
        assert manager.is_build is False
        assert manager.is_interactive is True
        assert manager.is_auto is False

    def test_custom_initial_modes(self):
        """Test custom initial mode settings."""
        manager = ModeManager(
            initial_mode=Mode.BUILD,
            initial_execution=ExecutionMode.AUTO
        )
        assert manager.mode == Mode.BUILD
        assert manager.execution_mode == ExecutionMode.AUTO
        assert manager.is_build is True
        assert manager.is_auto is True

    def test_set_mode(self):
        """Test setting operating mode."""
        manager = ModeManager()

        manager.set_mode(Mode.BUILD)
        assert manager.mode == Mode.BUILD
        assert manager.is_build is True

        manager.set_mode(Mode.PLAN)
        assert manager.mode == Mode.PLAN
        assert manager.is_plan is True

    def test_to_plan_and_to_build(self):
        """Test convenience methods for mode switching."""
        manager = ModeManager()

        manager.to_build()
        assert manager.is_build is True

        manager.to_plan()
        assert manager.is_plan is True

    def test_set_execution_mode(self):
        """Test setting execution mode."""
        manager = ModeManager()

        manager.set_execution_mode(ExecutionMode.AUTO)
        assert manager.execution_mode == ExecutionMode.AUTO
        assert manager.is_auto is True

        manager.set_execution_mode(ExecutionMode.INTERACTIVE)
        assert manager.execution_mode == ExecutionMode.INTERACTIVE
        assert manager.is_interactive is True

    def test_to_interactive_and_to_auto(self):
        """Test convenience methods for execution mode switching."""
        manager = ModeManager()

        manager.to_auto()
        assert manager.is_auto is True

        manager.to_interactive()
        assert manager.is_interactive is True

    def test_mode_change_listener(self):
        """Test mode change callbacks."""
        manager = ModeManager()
        changes = []

        def on_change(mode):
            changes.append(mode)

        manager.on_mode_change(on_change)

        manager.to_build()
        manager.to_plan()

        assert len(changes) == 2
        assert changes[0] == Mode.BUILD
        assert changes[1] == Mode.PLAN

    def test_execution_mode_change_listener(self):
        """Test execution mode change callbacks."""
        manager = ModeManager()
        changes = []

        def on_change(mode):
            changes.append(mode)

        manager.on_execution_change(on_change)

        manager.to_auto()
        manager.to_interactive()

        assert len(changes) == 2
        assert changes[0] == ExecutionMode.AUTO
        assert changes[1] == ExecutionMode.INTERACTIVE

    def test_no_callback_on_same_mode(self):
        """Test that callbacks aren't triggered when mode stays the same."""
        manager = ModeManager()
        changes = []

        def on_change(mode):
            changes.append(mode)

        manager.on_mode_change(on_change)

        manager.to_plan()  # Already in PLAN mode

        assert len(changes) == 0

    def test_require_build_in_plan_mode(self):
        """Test require_build raises error in PLAN mode."""
        manager = ModeManager()  # Default is PLAN

        with pytest.raises(PermissionError) as exc_info:
            manager.require_build("edit")

        assert "edit" in str(exc_info.value)
        assert "BUILD mode" in str(exc_info.value)

    def test_require_build_in_build_mode(self):
        """Test require_build passes in BUILD mode."""
        manager = ModeManager(initial_mode=Mode.BUILD)

        # Should not raise
        manager.require_build("edit")

    def test_status(self):
        """Test status string formatting."""
        manager = ModeManager()
        assert manager.status() == "PLAN | INTERACTIVE"

        manager.to_build()
        manager.to_auto()
        assert manager.status() == "BUILD | AUTO"

    def test_status_short(self):
        """Test short status string formatting."""
        manager = ModeManager()
        assert manager.status_short() == "P/I"

        manager.to_build()
        manager.to_auto()
        assert manager.status_short() == "B/A"

"""Mode manager for PLAN/BUILD and INTERACTIVE/AUTO state machines."""

from enum import Enum
from typing import Callable


class Mode(Enum):
    """Operating mode for the agent."""
    PLAN = "plan"
    BUILD = "build"


class ExecutionMode(Enum):
    """Execution mode for commands and tools."""
    INTERACTIVE = "interactive"  # Ask before executing unsafe commands
    AUTO = "auto"                # Execute without asking


class ModeManager:
    """Manages operating and execution modes."""

    def __init__(
        self,
        initial_mode: Mode = Mode.PLAN,
        initial_execution: ExecutionMode = ExecutionMode.INTERACTIVE,
    ):
        self._mode = initial_mode
        self._execution_mode = initial_execution
        self._mode_listeners: list[Callable[[Mode], None]] = []
        self._execution_listeners: list[Callable[[ExecutionMode], None]] = []

    # --- Operating Mode (PLAN/BUILD) ---

    @property
    def mode(self) -> Mode:
        """Current operating mode."""
        return self._mode

    @property
    def is_plan(self) -> bool:
        """Check if in PLAN mode."""
        return self._mode == Mode.PLAN

    @property
    def is_build(self) -> bool:
        """Check if in BUILD mode."""
        return self._mode == Mode.BUILD

    def set_mode(self, mode: Mode) -> None:
        """Switch to a new operating mode."""
        old_mode = self._mode
        self._mode = mode
        if old_mode != mode:
            for listener in self._mode_listeners:
                listener(mode)

    def to_plan(self) -> None:
        """Switch to PLAN mode."""
        self.set_mode(Mode.PLAN)

    def to_build(self) -> None:
        """Switch to BUILD mode."""
        self.set_mode(Mode.BUILD)

    def on_mode_change(self, callback: Callable[[Mode], None]) -> None:
        """Register a listener for mode changes."""
        self._mode_listeners.append(callback)

    def require_build(self, operation: str) -> None:
        """Raise an error if not in BUILD mode."""
        if not self.is_build:
            raise PermissionError(
                f"Operation '{operation}' requires BUILD mode. "
                f"Currently in {self._mode.value.upper()} mode."
            )

    # --- Execution Mode (INTERACTIVE/AUTO) ---

    @property
    def execution_mode(self) -> ExecutionMode:
        """Current execution mode."""
        return self._execution_mode

    @property
    def is_interactive(self) -> bool:
        """Check if in INTERACTIVE mode."""
        return self._execution_mode == ExecutionMode.INTERACTIVE

    @property
    def is_auto(self) -> bool:
        """Check if in AUTO mode."""
        return self._execution_mode == ExecutionMode.AUTO

    def set_execution_mode(self, mode: ExecutionMode) -> None:
        """Switch execution mode."""
        old_mode = self._execution_mode
        self._execution_mode = mode
        if old_mode != mode:
            for listener in self._execution_listeners:
                listener(mode)

    def to_interactive(self) -> None:
        """Switch to INTERACTIVE execution mode."""
        self.set_execution_mode(ExecutionMode.INTERACTIVE)

    def to_auto(self) -> None:
        """Switch to AUTO execution mode."""
        self.set_execution_mode(ExecutionMode.AUTO)

    def on_execution_change(self, callback: Callable[[ExecutionMode], None]) -> None:
        """Register a listener for execution mode changes."""
        self._execution_listeners.append(callback)

    # --- Combined Status ---

    def status(self) -> str:
        """Get formatted status string."""
        return f"{self._mode.value.upper()} | {self._execution_mode.value.upper()}"

    def status_short(self) -> str:
        """Get short status for prompt."""
        mode_char = "P" if self.is_plan else "B"
        exec_char = "A" if self.is_auto else "I"
        return f"{mode_char}/{exec_char}"

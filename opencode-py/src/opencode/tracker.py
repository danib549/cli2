"""Plan and task tracking."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TaskStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Task:
    """A single task in a plan."""
    description: str
    status: TaskStatus = TaskStatus.PENDING
    error: Optional[str] = None

    def mark_pending(self) -> None:
        self.status = TaskStatus.PENDING
        self.error = None

    def mark_in_progress(self) -> None:
        self.status = TaskStatus.IN_PROGRESS
        self.error = None

    def mark_done(self) -> None:
        self.status = TaskStatus.DONE
        self.error = None

    def mark_failed(self, error: str) -> None:
        self.status = TaskStatus.FAILED
        self.error = error

    def mark_skipped(self) -> None:
        self.status = TaskStatus.SKIPPED
        self.error = None


@dataclass
class Plan:
    """A plan with multiple tasks."""
    title: str
    tasks: list[Task] = field(default_factory=list)
    confirmed: bool = False

    def add_task(self, description: str, at_index: Optional[int] = None) -> Task:
        """Add a new task to the plan.

        Args:
            description: Task description.
            at_index: Optional index to insert at. If None, appends to end.
        """
        task = Task(description=description)
        if at_index is not None and 0 <= at_index <= len(self.tasks):
            self.tasks.insert(at_index, task)
        else:
            self.tasks.append(task)
        return task

    def remove_task(self, index: int) -> bool:
        """Remove a task by index (0-based).

        Returns:
            True if task was removed, False if index invalid.
        """
        if 0 <= index < len(self.tasks):
            self.tasks.pop(index)
            return True
        return False

    def edit_task(self, index: int, new_description: str) -> bool:
        """Edit a task's description.

        Returns:
            True if task was edited, False if index invalid.
        """
        if 0 <= index < len(self.tasks):
            self.tasks[index].description = new_description
            self.tasks[index].status = TaskStatus.PENDING
            return True
        return False

    def get_task(self, index: int) -> Optional[Task]:
        """Get task by index (0-based)."""
        if 0 <= index < len(self.tasks):
            return self.tasks[index]
        return None

    def mark_in_progress(self, index: int) -> None:
        """Mark a task as in progress."""
        if task := self.get_task(index):
            task.mark_in_progress()

    def mark_done(self, index: int) -> None:
        """Mark a task as done."""
        if task := self.get_task(index):
            task.mark_done()

    def mark_failed(self, index: int, error: str) -> None:
        """Mark a task as failed."""
        if task := self.get_task(index):
            task.mark_failed(error)

    def mark_skipped(self, index: int) -> None:
        """Mark a task as skipped."""
        if task := self.get_task(index):
            task.mark_skipped()

    def current_task_index(self) -> Optional[int]:
        """Get the index of the current task (first pending/in_progress)."""
        for i, task in enumerate(self.tasks):
            if task.status in (TaskStatus.PENDING, TaskStatus.IN_PROGRESS):
                return i
        return None

    def is_complete(self) -> bool:
        """Check if all tasks are done or skipped."""
        return all(
            t.status in (TaskStatus.DONE, TaskStatus.SKIPPED)
            for t in self.tasks
        )

    def progress_summary(self) -> str:
        """Get a short progress summary."""
        done = sum(1 for t in self.tasks if t.status == TaskStatus.DONE)
        total = len(self.tasks)
        return f"{done}/{total} completed"

    def render(self, width: int = 62) -> str:
        """Render plan as formatted box."""
        lines = []
        inner_width = width - 4  # Account for "| " and " |"

        # Header
        header = "BUILDING" if self.confirmed else "PLAN"
        title_text = f"{header}: {self.title}"
        if len(title_text) > inner_width:
            title_text = title_text[:inner_width - 3] + "..."

        lines.append(f"┌{'─' * (width - 2)}┐")
        lines.append(f"│ {title_text:<{inner_width}} │")
        lines.append(f"├{'─' * (width - 2)}┤")

        # Steps header
        lines.append(f"│{' ' * (width - 2)}│")
        lines.append(f"│  Steps:{' ' * (inner_width - 7)} │")

        # Tasks
        for i, task in enumerate(self.tasks):
            icon = {
                TaskStatus.PENDING: " ",
                TaskStatus.IN_PROGRESS: ">",
                TaskStatus.DONE: "x",
                TaskStatus.FAILED: "!",
                TaskStatus.SKIPPED: "-",
            }[task.status]

            # Truncate description if needed
            desc = task.description
            max_desc_len = inner_width - 8  # "  [x] N. "
            if len(desc) > max_desc_len:
                desc = desc[:max_desc_len - 3] + "..."

            step_num = f"{i + 1}."
            line_content = f"  [{icon}] {step_num:<3} {desc}"
            lines.append(f"│ {line_content:<{inner_width}} │")

            # Show error if failed
            if task.status == TaskStatus.FAILED and task.error:
                error_text = f"      Error: {task.error}"
                if len(error_text) > inner_width:
                    error_text = error_text[:inner_width - 3] + "..."
                lines.append(f"│ {error_text:<{inner_width}} │")

        lines.append(f"│{' ' * (width - 2)}│")

        # Footer with confirmation prompt or progress
        if not self.confirmed:
            lines.append(f"├{'─' * (width - 2)}┤")
            lines.append(f"│ {'Commands:':<{inner_width}} │")
            lines.append(f"│ {'  yes/build - Execute this plan':<{inner_width}} │")
            lines.append(f"│ {'  revise <feedback> - Ask AI to modify plan':<{inner_width}} │")
            lines.append(f"│ {'  add/edit/remove <N> - Manual edits':<{inner_width}} │")
            lines.append(f"│ {'  cancel  - Discard this plan':<{inner_width}} │")
        else:
            progress = self.progress_summary()
            lines.append(f"│ {progress:<{inner_width}} │")

        lines.append(f"└{'─' * (width - 2)}┘")

        return "\n".join(lines)

    def render_compact(self) -> str:
        """Render a compact single-line progress (ASCII-safe for Windows)."""
        icons = []
        for task in self.tasks:
            icon = {
                TaskStatus.PENDING: "o",
                TaskStatus.IN_PROGRESS: "*",
                TaskStatus.DONE: "X",
                TaskStatus.FAILED: "!",
                TaskStatus.SKIPPED: "-",
            }[task.status]
            icons.append(icon)

        return f"[{' '.join(icons)}] {self.progress_summary()}"


class PlanTracker:
    """Manages the current plan and execution state."""

    def __init__(self):
        self.current_plan: Optional[Plan] = None
        self.history: list[Plan] = []

    def create_plan(self, title: str, tasks: list[str] = None) -> Plan:
        """Create a new plan."""
        plan = Plan(title=title)
        if tasks:
            for task_desc in tasks:
                plan.add_task(task_desc)
        self.current_plan = plan
        return plan

    def confirm_plan(self) -> bool:
        """Confirm the current plan for execution."""
        if self.current_plan:
            self.current_plan.confirmed = True
            return True
        return False

    def complete_plan(self) -> None:
        """Archive current plan and clear."""
        if self.current_plan:
            self.history.append(self.current_plan)
            self.current_plan = None

    def has_active_plan(self) -> bool:
        """Check if there's an active plan."""
        return self.current_plan is not None

    def is_plan_confirmed(self) -> bool:
        """Check if current plan is confirmed."""
        return self.current_plan is not None and self.current_plan.confirmed

    def render(self) -> str:
        """Render current plan or empty message."""
        if self.current_plan:
            return self.current_plan.render()
        return "[No active plan]"

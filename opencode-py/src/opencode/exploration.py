"""Exploration Guard - Enforces read-before-write discipline.

This module implements an "aggressive teacher" pattern that REQUIRES
the LLM to explore and understand code before modifying it.

Philosophy:
- You cannot fix what you don't understand
- You cannot write quality code without reading existing patterns
- Exploration is not optional, it's mandatory
- The LLM must EARN the right to write by demonstrating comprehension
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ExplorationState:
    """Tracks what has been explored in the session."""

    # Files that have been explicitly read
    files_read: set[str] = field(default_factory=set)

    # Directories explored via Glob
    dirs_globbed: set[str] = field(default_factory=set)

    # Patterns searched via Grep
    patterns_grepped: set[str] = field(default_factory=set)

    # Paths searched via Grep
    paths_grepped: set[str] = field(default_factory=set)

    # Total exploration actions (must meet minimum before any write)
    exploration_count: int = 0

    # Minimum exploration actions before writes are allowed
    MIN_EXPLORATION_ACTIONS: int = 2


@dataclass
class ExplorationViolation:
    """Details about why an operation was blocked."""

    blocked: bool
    reason: str
    required_actions: list[str]
    teaching_message: str


class ExplorationGuard:
    """
    Enforces exploration before modification.

    Acts as an "aggressive teacher" that blocks write operations
    until the LLM has demonstrated it understands the codebase.

    Rules:
    1. Before ANY write/edit, must have done at least 2 exploration actions
    2. Before edit, MUST have read the target file
    3. Before write to existing file, MUST have read it first
    4. Before creating new file, MUST have globbed the target directory
    """

    # Exploration tools (read-only, understanding-focused)
    EXPLORATION_TOOLS = frozenset({"read", "glob", "grep", "tree", "outline",
                                    "find_definition", "find_references", "find_symbols"})

    # Modification tools (require prior exploration)
    MODIFICATION_TOOLS = frozenset({"write", "edit", "rename_symbol"})

    def __init__(self, enabled: bool = True) -> None:
        """Initialize the exploration guard.

        Args:
            enabled: Whether to enforce exploration requirements.
        """
        self.enabled = enabled
        self.state = ExplorationState()

    def reset(self) -> None:
        """Reset exploration state (for new task)."""
        self.state = ExplorationState()

    def record_exploration(self, tool_name: str, args: dict[str, Any]) -> None:
        """
        Record an exploration action.

        Also records write/edit operations so that files you just created/modified
        can be edited again without needing to re-read them.

        Args:
            tool_name: The exploration tool used
            args: Tool arguments
        """
        tool_lower = tool_name.lower()

        # Handle modification tools - record the file as "known" so subsequent
        # edits don't require re-reading (you just wrote it, you know its contents)
        if tool_lower in ("write", "edit"):
            path = args.get("path", "")
            if path:
                normalized = self._normalize_path(path)
                self.state.files_read.add(normalized)
                # Also mark directory as explored
                parent = str(Path(normalized).parent)
                self.state.dirs_globbed.add(parent)
            return  # Don't count as exploration action

        if tool_lower not in self.EXPLORATION_TOOLS:
            return

        self.state.exploration_count += 1

        if tool_lower == "read":
            path = args.get("path", "")
            if path:
                normalized = self._normalize_path(path)
                self.state.files_read.add(normalized)
                # Also mark directory as partially explored
                parent = str(Path(normalized).parent)
                self.state.dirs_globbed.add(parent)

        elif tool_lower == "glob":
            pattern = args.get("pattern", "")
            path = args.get("path", "")  # Also consider the path argument
            if pattern:
                # Extract base directory from pattern
                base_dir = self._extract_base_dir(pattern)
                # Combine with path if provided
                if path:
                    from pathlib import Path as PathLib
                    full_dir = str(PathLib(path) / base_dir) if base_dir != "." else path
                else:
                    full_dir = base_dir
                self.state.dirs_globbed.add(self._normalize_path(full_dir))

        elif tool_lower == "grep":
            pattern = args.get("pattern", "")
            path = args.get("path", ".") or "."

            if pattern:
                self.state.patterns_grepped.add(pattern)
            normalized = self._normalize_path(path)
            self.state.paths_grepped.add(normalized)
            self.state.dirs_globbed.add(normalized)

        elif tool_lower == "tree":
            # Tree explores a directory - record it
            path = args.get("path", ".")
            normalized = self._normalize_path(path)
            self.state.dirs_globbed.add(normalized)

        elif tool_lower in ("outline", "find_definition",
                           "find_references", "find_symbols"):
            # These are exploratory tools - count them
            # outline also explores a file's directory
            path = args.get("path", "")
            if path:
                normalized = self._normalize_path(path)
                self.state.files_read.add(normalized)
                parent = str(Path(normalized).parent)
                self.state.dirs_globbed.add(parent)

    def check_modification(
        self, tool_name: str, args: dict[str, Any]
    ) -> ExplorationViolation:
        """
        Check if a modification is allowed based on prior exploration.

        Args:
            tool_name: The modification tool being used
            args: Tool arguments

        Returns:
            ExplorationViolation with details if blocked, or allowed=True
        """
        if not self.enabled:
            return ExplorationViolation(
                blocked=False,
                reason="Exploration guard disabled",
                required_actions=[],
                teaching_message="",
            )

        tool_lower = tool_name.lower()
        if tool_lower not in self.MODIFICATION_TOOLS:
            return ExplorationViolation(
                blocked=False,
                reason="Not a modification tool",
                required_actions=[],
                teaching_message="",
            )

        path = args.get("path", "")
        if not path:
            return ExplorationViolation(
                blocked=True,
                reason="No path provided",
                required_actions=["Provide a path argument"],
                teaching_message="You must specify which file to modify.",
            )

        normalized_path = self._normalize_path(path)
        parent_dir = str(Path(normalized_path).parent)
        file_exists = os.path.exists(normalized_path)

        required_actions: list[str] = []

        # Check if target directory was explored (used for lenient new file creation)
        dir_explored = self._directory_explored(parent_dir)
        # Check if file is already known (read or created by us)
        file_known = normalized_path in self.state.files_read

        # Rule 1: Minimum exploration count
        # Exceptions for lenient handling:
        # - New file creation in explored directory: 1 action enough
        # - Editing a file we already read/created: 1 action enough
        min_required = self.state.MIN_EXPLORATION_ACTIONS
        if tool_lower == "write" and not file_exists and dir_explored:
            min_required = 1  # Lenient for new files in explored directories
        elif tool_lower == "write" and file_exists and file_known:
            min_required = 1  # Lenient for overwriting files we already know
        elif tool_lower == "edit" and file_known:
            min_required = 1  # Lenient for editing files we already know

        if self.state.exploration_count < min_required:
            remaining = min_required - self.state.exploration_count
            required_actions.append(
                f"Perform at least {remaining} more exploration action(s) "
                f"(read, glob, grep, tree, outline) before modifying files"
            )

        # Rule 2: For edit, MUST have read the file
        if tool_lower == "edit":
            if normalized_path not in self.state.files_read:
                required_actions.append(
                    f"Read the file first: read(\"{path}\")"
                )

        # Rule 3: For write to existing file, should have read it
        if tool_lower == "write" and file_exists:
            if normalized_path not in self.state.files_read:
                required_actions.append(
                    f"You're overwriting an EXISTING file! Read it first to understand "
                    f"what you're replacing: read(\"{path}\")"
                )

        # Rule 4: For new file, should have explored the directory
        if tool_lower == "write" and not file_exists:
            if not dir_explored:
                required_actions.append(
                    f"Explore the target directory first to understand existing patterns: "
                    f"glob(\"{parent_dir}/*\") or tree(\"{parent_dir}\")"
                )

        if required_actions:
            teaching_message = self._build_teaching_message(
                tool_name, path, required_actions
            )
            return ExplorationViolation(
                blocked=True,
                reason="Insufficient exploration before modification",
                required_actions=required_actions,
                teaching_message=teaching_message,
            )

        return ExplorationViolation(
            blocked=False,
            reason="Exploration requirements met",
            required_actions=[],
            teaching_message="",
        )

    def _normalize_path(self, path: str) -> str:
        """Normalize a path for consistent comparison."""
        if not path:
            return ""
        # Resolve to absolute path and normalize
        try:
            return str(Path(path).resolve())
        except (OSError, ValueError):
            return os.path.normpath(path)

    def _extract_base_dir(self, pattern: str) -> str:
        """Extract the base directory from a glob pattern."""
        parts = pattern.replace("\\", "/").split("/")
        base_parts = []
        for part in parts:
            if "*" in part or "?" in part or "[" in part:
                break
            base_parts.append(part)

        if not base_parts:
            return "."

        base = "/".join(base_parts)
        return self._normalize_path(base)

    def _directory_explored(self, directory: str) -> bool:
        """Check if a directory or any ancestor has been explored.

        This is important for creating files in NEW subdirectories.
        If user explored /project and wants to create /project/new_dir/file.c,
        we should allow it since /project was explored.
        """
        normalized = self._normalize_path(directory)

        # Check if this exact directory was explored
        if normalized in self.state.dirs_globbed:
            return True

        # Check if it was searched via grep
        if normalized in self.state.paths_grepped:
            return True

        # Walk up the directory tree to check ancestors
        # This handles creating files in NEW subdirectories
        try:
            current = Path(normalized)
            # Limit iterations to prevent infinite loops
            for _ in range(20):
                parent = current.parent
                if parent == current:  # Reached root
                    break
                parent_str = str(parent)
                if parent_str in self.state.dirs_globbed:
                    return True
                if parent_str in self.state.paths_grepped:
                    return True
                current = parent
        except (OSError, ValueError):
            pass

        return False

    def _build_teaching_message(
        self, tool_name: str, path: str, required_actions: list[str]
    ) -> str:
        """Build an aggressive, educational message about why the operation was blocked."""
        action_list = "\n".join(f"  {i+1}. {action}" for i, action in enumerate(required_actions))

        return f"""
================================================================================
                         EXPLORATION REQUIRED
================================================================================

You attempted to use {tool_name} on "{path}" WITHOUT proper exploration.

This is NOT allowed. You MUST understand code before modifying it.

REQUIRED ACTIONS BEFORE YOU CAN PROCEED:
{action_list}

WHY THIS MATTERS:
- Blindly writing code leads to bugs and inconsistencies
- You might duplicate existing functionality
- You might break existing patterns or conventions
- You might introduce security vulnerabilities
- You CANNOT write good code without reading existing code first

WHAT TO DO NOW:
1. Stop trying to modify files
2. Use read, glob, grep, tree, or outline to explore the codebase
3. Understand the existing patterns and conventions
4. THEN and ONLY THEN, proceed with your modification

This is non-negotiable. Explore first, modify second.
================================================================================
"""

    def get_exploration_summary(self) -> dict[str, Any]:
        """Get a summary of exploration state for debugging."""
        return {
            "files_read": list(self.state.files_read),
            "dirs_globbed": list(self.state.dirs_globbed),
            "patterns_grepped": list(self.state.patterns_grepped),
            "paths_grepped": list(self.state.paths_grepped),
            "exploration_count": self.state.exploration_count,
            "min_required": self.state.MIN_EXPLORATION_ACTIONS,
            "can_modify": self.state.exploration_count >= self.state.MIN_EXPLORATION_ACTIONS,
        }

    def format_status(self) -> str:
        """Format a brief status for display."""
        count = self.state.exploration_count
        min_req = self.state.MIN_EXPLORATION_ACTIONS
        files = len(self.state.files_read)

        if count >= min_req:
            return f"[Explored: {count} actions, {files} files - OK to modify]"
        else:
            return f"[Explored: {count}/{min_req} actions - NEED MORE before modifying]"

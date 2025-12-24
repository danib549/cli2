"""Permission gate for tool and shell execution.

Includes ExplorationGuard integration for enforcing read-before-write.
"""

from enum import Enum
from typing import Optional, TYPE_CHECKING, Any

from opencode.style import yellow, green, red, cyan, bold
from opencode.exploration import ExplorationGuard, ExplorationViolation

if TYPE_CHECKING:
    from opencode.config import Config


class Permission(Enum):
    """Permission levels."""
    ASK = "ask"
    ALLOW = "allow"
    DENY = "deny"


class PermissionDenied(Exception):
    """Raised when a tool execution is denied."""
    pass


class FeedbackProvided(Exception):
    """Raised when user wants to give feedback instead of allowing/denying."""

    def __init__(self, feedback: str):
        self.feedback = feedback
        super().__init__(f"User feedback: {feedback}")


class ExplorationRequired(Exception):
    """Raised when modification attempted without sufficient exploration."""

    def __init__(self, violation: ExplorationViolation):
        self.violation = violation
        super().__init__(violation.reason)


class PermissionGate:
    """Interactive permission gate for tool and shell calls.

    Includes ExplorationGuard integration for enforcing exploration
    before modification (aggressive teacher mode).
    """

    def __init__(
        self,
        default: Permission = Permission.ASK,
        config: "Config" = None,
        auto_mode: bool = False,
        enforce_exploration: bool = True,
    ):
        """Initialize permission gate.

        Args:
            default: Default permission level.
            config: Optional config for safe command whitelist.
            auto_mode: If True, allow all without prompting.
            enforce_exploration: If True, require exploration before writes.
        """
        self._default = default
        self._rules: dict[str, Permission] = {}
        self._config = config
        self._auto_mode = auto_mode
        self._enforce_exploration = enforce_exploration
        self._exploration_guard = ExplorationGuard(enabled=enforce_exploration)

    @property
    def auto_mode(self) -> bool:
        """Check if auto-execution mode is enabled."""
        return self._auto_mode

    @auto_mode.setter
    def auto_mode(self, value: bool) -> None:
        """Set auto-execution mode."""
        self._auto_mode = value

    @property
    def exploration_guard(self) -> ExplorationGuard:
        """Get the exploration guard."""
        return self._exploration_guard

    @property
    def enforce_exploration(self) -> bool:
        """Check if exploration enforcement is enabled."""
        return self._enforce_exploration

    @enforce_exploration.setter
    def enforce_exploration(self, value: bool) -> None:
        """Enable/disable exploration enforcement."""
        self._enforce_exploration = value
        self._exploration_guard.enabled = value

    def record_tool_execution(self, tool_name: str, args: dict[str, Any]) -> None:
        """Record a tool execution for exploration tracking.

        Call this AFTER a tool successfully executes.

        Args:
            tool_name: Name of the executed tool
            args: Tool arguments
        """
        self._exploration_guard.record_exploration(tool_name, args)

    def check_exploration(self, tool_name: str, args: dict[str, Any]) -> ExplorationViolation:
        """Check if a modification is allowed based on exploration.

        Args:
            tool_name: Name of the tool
            args: Tool arguments

        Returns:
            ExplorationViolation with details
        """
        return self._exploration_guard.check_modification(tool_name, args)

    def reset_exploration(self) -> None:
        """Reset exploration state for a new task."""
        self._exploration_guard.reset()

    def exploration_status(self) -> str:
        """Get formatted exploration status."""
        return self._exploration_guard.format_status()

    def set_rule(self, tool_name: str, permission: Permission) -> None:
        """Set a permission rule for a specific tool."""
        self._rules[tool_name] = permission

    def get_permission(self, tool_name: str) -> Permission:
        """Get the permission level for a tool."""
        return self._rules.get(tool_name, self._default)

    def is_safe_command(self, command: str) -> bool:
        """Check if a shell command is in the safe whitelist."""
        if self._config:
            return self._config.is_safe_command(command)

        # Fallback safe commands if no config
        safe_prefixes = {
            "ls", "pwd", "cat", "head", "tail", "echo",
            "which", "whoami", "date", "wc", "file", "tree",
        }

        first_word = command.strip().split()[0].lower() if command.strip() else ""
        if first_word in safe_prefixes:
            return True

        # Git read-only
        cmd_lower = command.lower().strip()
        if cmd_lower.startswith(("git status", "git log", "git diff", "git branch")):
            return True

        return False

    def check(
        self,
        tool_name: str,
        description: str,
        prompt_fn: Optional[callable] = None
    ) -> bool:
        """Check if a tool call is permitted.

        Args:
            tool_name: Name of the tool being called.
            description: Human-readable description of what the tool will do.
            prompt_fn: Optional function to prompt user. If None, uses input().

        Returns:
            True if permitted, raises PermissionDenied if not.
        """
        # Auto mode allows everything
        if self._auto_mode:
            return True

        perm = self.get_permission(tool_name)

        if perm == Permission.ALLOW:
            return True

        if perm == Permission.DENY:
            raise PermissionDenied(f"Tool '{tool_name}' is denied by policy.")

        # ASK mode - prompt the user
        prompt_fn = prompt_fn or self._default_prompt
        response = prompt_fn(tool_name, description)

        if response == "allow":
            return True
        elif response == "always":
            self.set_rule(tool_name, Permission.ALLOW)
            return True
        elif response == "deny":
            raise PermissionDenied(f"User denied execution of '{tool_name}'.")
        elif response == "never":
            self.set_rule(tool_name, Permission.DENY)
            raise PermissionDenied(f"Tool '{tool_name}' denied permanently.")
        elif response.startswith("feedback:"):
            feedback_text = response[9:].strip()  # Remove "feedback:" prefix
            raise FeedbackProvided(feedback_text)
        else:
            raise PermissionDenied(f"Invalid response, denying '{tool_name}'.")

    def check_with_exploration(
        self,
        tool_name: str,
        args: dict[str, Any],
        description: str,
        prompt_fn: Optional[callable] = None
    ) -> bool:
        """Check both exploration requirements AND permissions.

        This is the main entry point for tool permission checks.
        It first checks exploration requirements (for write/edit tools),
        then checks user permissions.

        Args:
            tool_name: Name of the tool being called.
            args: Tool arguments (needed for exploration check).
            description: Human-readable description for prompting.
            prompt_fn: Optional function to prompt user.

        Returns:
            True if permitted.

        Raises:
            ExplorationRequired: If exploration requirements not met.
            PermissionDenied: If user denies permission.
            FeedbackProvided: If user provides feedback.
        """
        # First check exploration requirements for modification tools
        if self._enforce_exploration:
            violation = self.check_exploration(tool_name, args)
            if violation.blocked:
                raise ExplorationRequired(violation)

        # Then check normal permissions
        return self.check(tool_name, description, prompt_fn)

    def check_shell(
        self,
        command: str,
        prompt_fn: Optional[callable] = None
    ) -> bool:
        """Check if a shell command is permitted.

        Args:
            command: The shell command to check.
            prompt_fn: Optional function to prompt user.

        Returns:
            True if permitted, raises PermissionDenied if not.
        """
        # Auto mode allows everything
        if self._auto_mode:
            return True

        # Safe commands are auto-allowed (if configured)
        if self._config and self._config.auto_execute_safe:
            if self.is_safe_command(command):
                return True

        # Not safe - need to ask
        return self.check("bash", f"Run: {command}", prompt_fn)

    def _default_prompt(self, tool_name: str, description: str) -> str:
        """Default interactive prompt."""
        import sys

        # Box-style permission prompt (ASCII for cross-platform)
        print()
        print(yellow(f"+-- PERMISSION: {tool_name} " + "-" * (40 - len(tool_name)) + "+"))
        for line in description.split("\n"):
            print(f"|  {line}")
        print("+" + "-" * 57 + "+")
        print(f"|  {green('[a]llow')}  {green('[A]lways')}  {red('[d]eny')}  {red('[N]ever')}  {cyan('[f]eedback')}")
        print("+" + "-" * 57 + "+")

        # Check if stdin is interactive
        if not sys.stdin.isatty():
            print("  > [Auto-allowing in non-interactive mode]")
            return "allow"

        try:
            response = input("  > ").strip().lower()
        except EOFError:
            print("  > [Auto-allowing on EOF]")
            return "allow"

        # Handle feedback option - ask for the feedback text
        if response in ("f", "feedback"):
            print(cyan("  What should the AI do instead?"))
            try:
                feedback_text = input("  > ").strip()
                if feedback_text:
                    return f"feedback:{feedback_text}"
                else:
                    print("  [No feedback provided, denying]")
                    return "deny"
            except EOFError:
                return "deny"

        mapping = {
            "a": "allow",
            "allow": "allow",
            "always": "always",
            "d": "deny",
            "deny": "deny",
            "n": "never",
            "never": "never",
        }
        return mapping.get(response, "deny")

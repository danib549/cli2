"""CLI entry point and chat-first REPL."""

import click
import atexit
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional

# Cross-platform readline support
try:
    import readline
except ImportError:
    # Windows doesn't have readline, try pyreadline3
    try:
        import pyreadline3 as readline
    except ImportError:
        readline = None  # No readline support


def _enable_windows_ansi():
    """Enable ANSI escape code support on Windows.

    Windows 10+ supports ANSI codes but they need to be enabled.
    This function enables virtual terminal processing.
    """
    if os.name != 'nt':
        return  # Not Windows

    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32

        # Get stdout handle
        STD_OUTPUT_HANDLE = -11
        handle = kernel32.GetStdHandle(STD_OUTPUT_HANDLE)

        # Get current console mode
        mode = ctypes.c_ulong()
        kernel32.GetConsoleMode(handle, ctypes.byref(mode))

        # Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004)
        ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        kernel32.SetConsoleMode(handle, mode.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING)
    except Exception:
        # Fallback: os.system('') trick also enables ANSI on some Windows versions
        os.system('')


# Enable ANSI colors on Windows
_enable_windows_ansi()


class StatusBar:
    """Fixed status bar at bottom of terminal for plan progress."""

    def __init__(self):
        self._enabled = True
        self._last_status = ""

    def update(self, plan) -> None:
        """Update the status bar with plan progress."""
        if not self._enabled or not plan:
            return

        # Build status line
        icons = []
        for task in plan.tasks:
            from opencode.tracker import TaskStatus
            icon = {
                TaskStatus.PENDING: "[ ]",
                TaskStatus.IN_PROGRESS: "[>]",
                TaskStatus.DONE: "[X]",
                TaskStatus.FAILED: "[!]",
                TaskStatus.SKIPPED: "[-]",
            }[task.status]
            icons.append(icon)

        done = sum(1 for t in plan.tasks if t.status == TaskStatus.DONE)
        total = len(plan.tasks)
        status = f" {' '.join(icons)} | {done}/{total} steps "

        # Print status line with separator
        print("-" * 60)
        print(f"[{status}]")

    def clear(self) -> None:
        """Clear the status bar."""
        pass  # Just let output scroll naturally


class Spinner:
    """Simple spinner for LLM response waiting indicator."""

    FRAMES = ["-", "\\", "|", "/"]  # ASCII spinner

    def __init__(self, message: str = "Thinking"):
        self.message = message
        self._running = False
        self._thread = None

    def _spin(self):
        idx = 0
        while self._running:
            frame = self.FRAMES[idx % len(self.FRAMES)]
            sys.stdout.write(f"\r[{frame}] {self.message}...")
            sys.stdout.flush()
            idx += 1
            time.sleep(0.1)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=0.5)
        # Clear the spinner line and move to new line
        sys.stdout.write("\r" + " " * (len(self.message) + 15) + "\r")
        sys.stdout.flush()


class CancellableLLMCall:
    """Run LLM calls in a thread so Ctrl+C can cancel them immediately."""

    def __init__(self):
        self._result = None
        self._error = None
        self._cancelled = False
        self._done = threading.Event()

    def run(self, fn, *args, **kwargs):
        """Run function in thread, return result or raise on cancel/error."""
        self._result = None
        self._error = None
        self._cancelled = False
        self._done.clear()

        def worker():
            try:
                self._result = fn(*args, **kwargs)
            except Exception as e:
                self._error = e
            finally:
                self._done.set()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()

        # Wait for completion, checking for KeyboardInterrupt
        while not self._done.is_set():
            try:
                # Short wait allows Ctrl+C to be caught
                if self._done.wait(timeout=0.1):
                    break
            except KeyboardInterrupt:
                self._cancelled = True
                raise

        if self._error:
            raise self._error

        return self._result

from opencode.config import Config
from opencode.workspace import Workspace, ensure_global_config
from opencode.mode import Mode, ExecutionMode, ModeManager
from opencode.permissions import PermissionGate, Permission, PermissionDenied, FeedbackProvided
from opencode.classifier import Classifier, InputType
from opencode.complexity import ComplexityAnalyzer
from opencode.tracker import PlanTracker, TaskStatus
from opencode.git import GitCheckpoint, create_checkpoint_fn
from opencode.session import SessionManager, format_session_list
from opencode.style import dim, bold, green, red, yellow, cyan, separator

from opencode.tools import ToolRegistry, ToolResult
from opencode.tools.read import ReadTool
from opencode.tools.edit import EditTool
from opencode.tools.write import WriteTool
from opencode.tools.bash import BashTool
from opencode.tools.glob import GlobTool
from opencode.tools.grep import GrepTool

from opencode.llm import (
    LLMProvider, LLMResponse, Message, ToolResult,
    AnthropicProvider, OpenAIProvider, CustomLLMProvider,
    PlanParser, format_plan_prompt
)


SYSTEM_PROMPT = """You are OpenCode, a local-first coding agent.

# Environment
- Mode: {mode}
- Working directory: {cwd}
- Workspace: {workspace_status}

# Tools
{tools}

{mode_instructions}

{plan_instructions}
{project_instructions}
"""

PLAN_MODE_INSTRUCTIONS = """# PLAN Mode

Read-only advisory phase. Explore and plan before executing.

## Your Role
1. **Understand** - Ask questions to fully understand requirements
2. **Explore** - Use read-only tools to analyze the codebase
3. **Advise** - Share recommendations, concerns, and tradeoffs
4. **Plan** - Propose a clear, structured approach

## Available Tools (Read-Only)
- `read`, `glob`, `grep` - Find and read files
- `tree`, `outline` - View structure
- `find_definition`, `find_references`, `find_symbols` - Navigate code
- NO: `write`, `edit`, `bash`, `rename_symbol`

## Be Proactive - Ask About:
- Specific requirements or constraints
- Preferred technologies or patterns
- Edge cases and error handling
- Testing requirements
- Performance or security concerns

## When to Ask vs Plan

### Ask FIRST when:
- Requirements are vague or incomplete
- Multiple valid approaches exist
- You see potential issues user should know about
- Trade-offs need user input

### Propose Plan when:
- You understand the requirements clearly
- You've explored the relevant code
- You can recommend a specific approach

## Guidance Style
- If multiple approaches exist, explain tradeoffs and recommend one
- If you see risks, warn the user
- If something is unclear, ask before assuming
- Keep explanations concise but complete

## Plan Format
```
## Plan: [Title]

### Summary
Brief description of the approach.

### Steps
1. First step - what and why
2. Second step - what and why
...

### Considerations
- Any risks or tradeoffs
- Alternative approaches (if relevant)
```

Keep plans concrete and actionable. Each step should be clear enough to execute.
"""

def _format_tool_description(tool_name: str, args: dict) -> str:
    """Format tool call for readable display.

    Instead of dumping raw args with huge content, show a summary.
    """
    if tool_name == "write":
        path = args.get("path", "?")
        content = args.get("content", "")
        lines = content.count("\n") + 1
        size = len(content)
        # Show first line or file type hint
        first_line = content.split("\n")[0][:60] if content else ""
        if len(first_line) == 60:
            first_line += "..."
        return f"Write to '{path}' ({lines} lines, {size} bytes)\n    First line: {first_line}"

    elif tool_name == "edit":
        path = args.get("path", "?")
        old = args.get("old_string", "")
        new = args.get("new_string", "")
        old_preview = old[:50].replace("\n", "\\n") + ("..." if len(old) > 50 else "")
        new_preview = new[:50].replace("\n", "\\n") + ("..." if len(new) > 50 else "")
        return f"Edit '{path}'\n    Replace: \"{old_preview}\"\n    With:    \"{new_preview}\""

    elif tool_name == "bash":
        cmd = args.get("command", "?")
        return f"Run command: {cmd}"

    elif tool_name == "read":
        path = args.get("path", "?")
        return f"Read file: {path}"

    else:
        # Generic fallback - truncate long values
        formatted = []
        for k, v in args.items():
            if isinstance(v, str) and len(v) > 100:
                v = v[:100] + "..."
            formatted.append(f"{k}={repr(v)}")
        return f"{tool_name}({', '.join(formatted)})"


BUILD_MODE_INSTRUCTIONS = """# BUILD Mode

You are a coding agent. You can read, write, and execute.

## Tool Categories

### Discovery
- `glob(pattern)` - Find files: `glob("**/*.py")`, `glob("src/**/*.ts")`
- `grep(pattern)` - Search content: `grep("def login")`, `grep("TODO", output_mode="count")`
- `tree(path, depth)` - Directory structure: `tree("src", depth=2)`

### Code Navigation
- `find_definition(symbol)` - Where is it defined: `find_definition("UserService")`
- `find_references(symbol)` - Where is it used: `find_references("authenticate")`
- `find_symbols(query)` - Search symbols: `find_symbols("*Handler")`
- `outline(path)` - File structure: `outline("src/auth.py")`

### Read & Write
- `read(path)` - Read file content
- `write(path, content)` - Create or overwrite file
- `edit(path, old, new)` - Replace specific text

### Refactoring
- `rename_symbol(old, new, language)` - Rename across files

### Execution
- `bash(command)` - Run shell commands

## Grep Features
```
grep("pattern", output_mode="files_with_matches")  # Just file names
grep("pattern", output_mode="count")               # Match counts
grep("pattern", context=2)                         # Lines before/after
grep("class.*:", multiline=True)                   # Match across lines
```

## When to ASK vs ACT

### ASK FIRST when:
- Multiple valid approaches exist and choice matters
- Request is ambiguous about what to build
- You see a potential issue user might not know
- Change could affect other parts of the system
- You need clarification on requirements

### ACT IMMEDIATELY when:
- Task is clear and straightforward
- User already specified their preference
- It's an obvious bug fix
- Small change with limited impact

## Workflow

### Creating NEW code
```
write("src/utils/helper.py", content)
```
Use `write` directly. Don't search for files that don't exist.

### Editing EXISTING code
```
grep("def login") → read("src/auth.py") → edit("src/auth.py", old, new)
```
Complete ALL steps in ONE turn. Don't stop after finding files.

### Understanding code
```
tree("src") → outline("src/main.py") → find_references("handle_request")
```

## Intent → Tools

| Intent | Tools |
|--------|-------|
| Create/Build/Add | `write` directly |
| Fix/Debug | `grep` → `read` → `edit` |
| Refactor/Rename | `find_references` → `rename_symbol` or `edit` |
| Understand | `outline`, `find_definition`, `tree` |
| Find | `grep`, `glob`, `find_symbols` |
| Run/Test | `bash` |

## Error Recovery

When a command fails, don't just report - try to fix it:

1. **Missing module**: `bash("pip install X")` then retry
2. **File not found**: Use glob/grep to find correct path
3. **Permission denied**: Suggest fix or try alternative
4. **Syntax error**: Fix and retry immediately

Don't give up after one failure. Be resourceful.

## Fix Similar Errors

When you find or fix a bug, ALWAYS check for similar issues elsewhere:

1. **After fixing a bug**: Use `grep` or `find_references` to find similar patterns
2. **Same mistake elsewhere**: If you find `foo == None`, search for other `== None` that should be `is None`
3. **Copy-paste errors**: If code was duplicated, the bug might exist in all copies
4. **Related functions**: If `save()` had a bug, check `load()`, `update()`, `delete()` too

Example workflow:
```
# Found bug: missing null check in user.py
edit("user.py", old, new)  # Fix the bug

# Check for similar issues
grep("\\.name", file_pattern="*.py")  # Find other .name accesses
grep("user\\.", file_pattern="*.py")  # Find other user. accesses
```

Be proactive - don't wait for the user to find related bugs.

## Verify Task Completion

Before finishing, ALWAYS verify your work:

1. **Summarize what was done**: Briefly list the changes made
2. **Check it works**: Run tests if asked or verify syntax
3. **Confirm the fix**: Re-read the changed code to ensure it's correct
4. **Look for side effects**: Did the change break anything else?

Example:
```
# After fixing a bug
bash("python -m py_compile src/auth.py")  # Verify syntax
bash("python -m pytest tests/test_auth.py")  # Run related tests

# Summary: Fixed null check in login() - added 'if user is None' guard
```

Never say "done" without verification. If you can't verify, tell the user what to check.

## Bug Fix Summary

After fixing a bug, ALWAYS explain:

1. **What was the bug**: Describe the problem in simple terms
2. **Why it happened**: Root cause (if known)
3. **What the fix does**: How the code behaves now
4. **What changed**: Files and lines modified

Example summary:
```
BUG: Users could submit empty forms because validation ran after submission.

FIX: Moved validation check before the submit handler.

BEFORE: submit() -> validate() -> error (too late)
AFTER:  validate() -> submit() (blocked if invalid)

Changed: src/forms.py lines 42-45
```

This helps users understand what happened and verify the fix is correct.

## Guidelines

### DO:
- Ask clarifying questions when requirements are unclear
- Warn about potential issues BEFORE they cause problems
- Complete full workflow in one turn (find → read → edit)
- Explain briefly what you're doing and why
- Suggest better approaches if you see them
- Verify changes work (run tests when relevant)

### DON'T:
- Search for files you're about to create
- Stop after finding files - continue to read and edit
- Make assumptions when you should ask
- Over-explain or add unnecessary commentary
- Give up after first error

### CRITICAL - Permission Denied:
When a tool execution is DENIED by the user:
- Do NOT output the code or content you were trying to write
- Do NOT paste the file contents into chat
- Just say "Got it, [action] denied. What would you like me to do?"
- Keep response under 2 sentences

## Your Role

You are both ADVISOR and BUILDER:
- If you see a better way, suggest it before implementing
- If something is risky, warn the user
- If unclear, ask - don't guess
- Once path is clear, execute efficiently
"""


class OpenCodeREPL:
    """Interactive chat-first REPL for OpenCode-Py."""

    def __init__(self, config: Config = None, workspace: Workspace = None):
        # Initialize workspace (find existing or None)
        self.workspace = workspace or Workspace()

        # Load config with workspace
        self.config = config or Config.load(workspace=self.workspace)

        # Initialize mode manager
        self.mode_manager = ModeManager(
            initial_mode=Mode.BUILD,  # Start in BUILD for chat
            initial_execution=ExecutionMode.INTERACTIVE,
        )

        # Initialize permission gate
        self.permission_gate = PermissionGate(
            default=Permission.ASK,
            config=self.config,
            auto_mode=False,
        )

        # Initialize git checkpoints
        self.git = GitCheckpoint()
        self.checkpoint_fn = create_checkpoint_fn(self.git)

        # Initialize tool registry with workspace
        self.registry = ToolRegistry(
            mode_manager=self.mode_manager,
            config=self.config,
            checkpoint_fn=self.checkpoint_fn,
            workspace=self.workspace,
        )
        self._register_tools()

        # Initialize classifiers and analyzers
        self.classifier = Classifier()
        self.complexity = ComplexityAnalyzer(
            threshold=self.config.complexity_threshold
        )

        # Initialize plan tracking
        self.plan_tracker = PlanTracker()
        self.plan_parser = PlanParser()

        # Initialize session manager
        self.session_manager = SessionManager(
            workspace_root=Path(self.workspace.root) if self.workspace.is_initialized else Path.cwd()
        )
        self.current_session_id = None

        # Initialize LLM (may be None if no API key)
        self.llm: Optional[LLMProvider] = self._create_llm_provider()

        # Chat history
        self.history: list[Message] = []

        # Mode change listeners
        self.mode_manager.on_mode_change(self._on_mode_change)
        self.mode_manager.on_execution_change(self._on_execution_change)

        # Setup readline for arrow key navigation and history
        self._setup_readline()

    def _register_tools(self) -> None:
        """Register all available tools via auto-discovery."""
        # Auto-discover all tools in the opencode.tools package
        count = self.registry.discover()
        # If discovery fails, manually register core tools
        if count == 0:
            self.registry.register(ReadTool)
            self.registry.register(GlobTool)
            self.registry.register(GrepTool)
            self.registry.register(EditTool)
            self.registry.register(WriteTool)
            self.registry.register(BashTool)

    def _setup_readline(self) -> None:
        """Setup readline for arrow key navigation and history."""
        # Skip if readline not available (Windows without pyreadline3)
        if readline is None:
            self.history_file = None
            return

        # History file location
        if self.workspace.is_initialized:
            self.history_file = self.workspace.config_dir / "history"
        else:
            self.history_file = Path.home() / ".opencode" / "history"

        # Ensure directory exists
        self.history_file.parent.mkdir(parents=True, exist_ok=True)

        # Load existing history
        try:
            if self.history_file.exists():
                readline.read_history_file(str(self.history_file))
        except Exception:
            pass  # Ignore history loading errors

        # Set history length
        readline.set_history_length(1000)

        # Save history on exit
        atexit.register(self._save_history)

    def _save_history(self) -> None:
        """Save readline history to file."""
        if readline is None or self.history_file is None:
            return
        try:
            readline.write_history_file(str(self.history_file))
        except Exception:
            pass  # Ignore history saving errors

    def _create_llm_provider(self) -> LLMProvider:
        """Create LLM provider based on config."""
        provider = self.config.llm_provider.lower()

        if provider == "anthropic":
            if not self.config.api_key:
                return None
            return AnthropicProvider(
                api_key=self.config.api_key,
                model=self.config.llm_model,
            )

        elif provider == "openai":
            if not self.config.api_key:
                return None
            return OpenAIProvider(
                api_key=self.config.api_key,
                model=self.config.llm_model,
                base_url=self.config.base_url or None,
            )

        elif provider == "custom":
            if not self.config.base_url:
                return None
            return CustomLLMProvider(
                base_url=self.config.base_url,
                model=self.config.llm_model,
                api_key=self.config.api_key or "not-needed",
            )

        return None

    def _on_mode_change(self, new_mode: Mode) -> None:
        """Handle operating mode changes."""
        print(f"\n[MODE] Switched to {new_mode.value.upper()} mode")

    def _on_execution_change(self, new_mode: ExecutionMode) -> None:
        """Handle execution mode changes."""
        self.permission_gate.auto_mode = (new_mode == ExecutionMode.AUTO)
        print(f"[EXEC] Switched to {new_mode.value.upper()} mode")

    def _get_prompt(self) -> str:
        """Generate the REPL prompt."""
        status = self.mode_manager.status_short()
        cwd = Path.cwd().name
        return f"[{status}] {cwd}> "

    def _get_system_prompt(self) -> str:
        """Generate system prompt for LLM."""
        plan_instructions = ""
        if self.config.auto_plan_enabled:
            plan_instructions = format_plan_prompt()

        # Workspace status
        if self.workspace.is_initialized:
            workspace_status = f"Initialized at {self.workspace.root}"
        else:
            workspace_status = "Not initialized (run /init or 'opencode init')"

        # Mode-specific instructions
        if self.mode_manager.is_plan:
            mode_instructions = PLAN_MODE_INSTRUCTIONS
        else:
            mode_instructions = BUILD_MODE_INSTRUCTIONS

        # Load project instructions from iai.md
        project_instructions = self._load_project_instructions()

        return SYSTEM_PROMPT.format(
            mode=self.mode_manager.mode.value.upper(),
            cwd=Path.cwd(),
            workspace_status=workspace_status,
            tools=self.registry.get_tool_descriptions(),
            mode_instructions=mode_instructions,
            plan_instructions=plan_instructions,
            project_instructions=project_instructions,
        )

    def _load_project_instructions(self) -> str:
        """Load project instructions from iai.md file.

        Searches for iai.md in:
        1. Workspace root (if initialized)
        2. Current working directory

        Returns:
            Formatted project instructions or empty string if not found.
        """
        iai_paths = []

        # Check workspace root first
        if self.workspace.is_initialized and self.workspace.root:
            iai_paths.append(self.workspace.root / "iai.md")

        # Then check current directory
        iai_paths.append(Path.cwd() / "iai.md")

        for iai_path in iai_paths:
            if iai_path.exists():
                try:
                    content = iai_path.read_text(encoding="utf-8")
                    return f"""
## Project Instructions (from iai.md)

The following instructions are specific to this project. Follow them carefully:

{content}
"""
                except Exception:
                    pass  # Ignore read errors

        return ""

    def _find_iai_file(self) -> Optional[Path]:
        """Find iai.md file in workspace or current directory.

        Returns:
            Path to iai.md if found, None otherwise.
        """
        # Check workspace root first
        if self.workspace.is_initialized and self.workspace.root:
            iai_path = self.workspace.root / "iai.md"
            if iai_path.exists():
                return iai_path

        # Then check current directory
        iai_path = Path.cwd() / "iai.md"
        if iai_path.exists():
            return iai_path

        return None

    def run(self) -> None:
        """Run the REPL loop."""
        print("OpenCode-Py v0.1.0")
        print(f"Provider: {self.config.llm_provider} | Model: {self.config.llm_model}")
        print(f"Mode: {self.mode_manager.status()}")

        if self.workspace.is_initialized:
            print(f"Workspace: {self.workspace.root}")
        else:
            print("Workspace: Not initialized (run /init to restrict file access)")

        # Check for project instructions
        iai_path = self._find_iai_file()
        if iai_path:
            print(green(f"Project instructions: {iai_path}"))

        if not self.llm:
            print("\n[Error] No LLM provider configured.")
            print("\nFor Anthropic (default):")
            print("  export ANTHROPIC_API_KEY='your-key-here'")
            print("\nFor OpenAI:")
            print("  export OPENAI_API_KEY='your-key-here'")
            print("\nFor custom providers (Ollama, LM Studio, etc.):")
            print("  export OPENCODE_BASE_URL='http://localhost:11434/v1'")
            print("  export OPENCODE_LLM_MODEL='llama3'")
            print("\nOr create ~/.opencode/config.toml - see /config for current settings")
            return

        print("\nType /help for commands, /quit to exit")
        print()

        while True:
            try:
                line = input(self._get_prompt()).strip()

                if not line:
                    continue

                self._handle_input(line)

            except KeyboardInterrupt:
                print("\n[Use /quit to exit]")
            except EOFError:
                break

        print("\nGoodbye.")

    def _handle_input(self, line: str) -> None:
        """Route input based on classification."""
        input_type = self.classifier.classify(line)

        if input_type == InputType.COMMAND:
            self._handle_command(line)
        elif input_type == InputType.SHELL:
            self._handle_shell(line)
        else:  # CHAT
            self._handle_chat(line)

    def _handle_command(self, line: str) -> None:
        """Handle slash commands."""
        cmd, args = self.classifier.extract_command(line)

        commands = {
            "help": self._cmd_help,
            "quit": self._cmd_quit,
            "exit": self._cmd_quit,
            "plan": self._cmd_plan,
            "build": self._cmd_build,
            "mode": self._cmd_mode,
            "auto": self._cmd_auto,
            "interactive": self._cmd_interactive,
            "tools": self._cmd_tools,
            "sensitivity": self._cmd_sensitivity,
            "config": self._cmd_config,
            "clear": self._cmd_clear,
            "init": self._cmd_init,
            "workspace": self._cmd_workspace,
            # Session commands
            "save": self._cmd_save,
            "load": self._cmd_load,
            "history": self._cmd_history,
            "sessions": self._cmd_sessions,
        }

        if cmd in commands:
            commands[cmd](args)
        else:
            print(f"Unknown command: /{cmd}")
            print("Type /help for available commands")

    def _handle_shell(self, command: str) -> None:
        """Handle detected shell command."""
        # Check if safe or need permission
        is_safe = self.permission_gate.is_safe_command(command)

        if is_safe and self.config.auto_execute_safe:
            print(f"[Safe command] Executing: {command}")
            self._execute_shell(command)
        else:
            # Ask for permission
            try:
                self.permission_gate.check_shell(command)
                self._execute_shell(command)
            except PermissionDenied as e:
                print(f"[Denied] {e}")

    def _execute_shell(self, command: str) -> None:
        """Execute a shell command via bash tool."""
        bash_tool = self.registry.get("bash")
        # Temporarily allow in any mode for direct shell execution
        old_mode = self.mode_manager.mode
        self.mode_manager.to_build()

        result = bash_tool.execute(command=command)

        self.mode_manager.set_mode(old_mode)

        if result.success:
            if result.output:
                print(result.output)
            else:
                print("[OK]")
        else:
            print(f"[Error] {result.error}")
            if result.output:
                print(result.output)

    def _handle_plan_command(self, user_input: str) -> bool:
        """Handle plan modification commands.

        Returns:
            True if input was handled as a plan command, False otherwise.
        """
        plan = self.plan_tracker.current_plan
        if not plan:
            return False

        parts = user_input.strip().split(maxsplit=2)
        cmd = parts[0].lower() if parts else ""

        # build - confirm and execute
        if cmd == "build":
            self._confirm_and_execute_plan()
            return True

        # cancel - discard the plan
        if cmd == "cancel":
            self.plan_tracker.current_plan = None
            self.mode_manager.to_build()
            print("[Plan cancelled]")
            return True

        # add <N> <description> - add step at position N
        if cmd == "add" and len(parts) >= 3:
            try:
                pos = int(parts[1])
                desc = parts[2]
                plan.add_task(desc, at_index=pos - 1)  # Convert to 0-indexed
                print(f"[Added step {pos}: {desc}]")
                print(plan.render())
                return True
            except ValueError:
                # If first arg isn't a number, append to end
                desc = " ".join(parts[1:])
                plan.add_task(desc)
                print(f"[Added step {len(plan.tasks)}: {desc}]")
                print(plan.render())
                return True

        # edit <N> <description> - edit step N
        if cmd == "edit" and len(parts) >= 3:
            try:
                pos = int(parts[1])
                desc = parts[2]
                if plan.edit_task(pos - 1, desc):  # Convert to 0-indexed
                    print(f"[Updated step {pos}]")
                    print(plan.render())
                else:
                    print(f"[Error] Invalid step number: {pos}")
                return True
            except ValueError:
                print("[Error] Usage: edit <N> <description>")
                return True

        # remove <N> - remove step N
        if cmd == "remove" and len(parts) >= 2:
            try:
                pos = int(parts[1])
                if plan.remove_task(pos - 1):  # Convert to 0-indexed
                    print(f"[Removed step {pos}]")
                    print(plan.render())
                else:
                    print(f"[Error] Invalid step number: {pos}")
                return True
            except ValueError:
                print("[Error] Usage: remove <N>")
                return True

        # show - re-display the plan
        if cmd in ("show", "plan"):
            print(plan.render())
            return True

        # revise <feedback> - ask LLM to revise the plan
        if cmd == "revise" and len(parts) >= 2:
            feedback = " ".join(parts[1:])
            self._revise_plan(feedback)
            return True

        # Not a plan command
        return False

    def _revise_plan(self, feedback: str) -> None:
        """Ask LLM to revise the current plan based on feedback."""
        plan = self.plan_tracker.current_plan
        if not plan:
            return

        # Build current plan as text
        current_steps = "\n".join(
            f"{i+1}. {t.description}" for i, t in enumerate(plan.tasks)
        )

        revision_prompt = f"""The current plan is:

{current_steps}

User feedback: {feedback}

Please revise the plan based on this feedback. Output the revised plan in the same format."""

        # Add to history and get LLM response (with streaming)
        self.history.append(Message(role="user", content=revision_prompt))

        llm_call = CancellableLLMCall()
        try:
            if hasattr(self.llm, 'chat_stream'):
                response = llm_call.run(
                    self.llm.chat_stream,
                    messages=self.history,
                    system=self._get_system_prompt(),
                )
            else:
                spinner = Spinner("Revising plan")
                spinner.start()
                try:
                    response = llm_call.run(
                        self.llm.chat,
                        messages=self.history,
                        system=self._get_system_prompt(),
                    )
                finally:
                    spinner.stop()
        except KeyboardInterrupt:
            print("\n[Cancelled by user]")
            return

        if response.content:
            self.history.append(Message(role="assistant", content=response.content))

            # Try to parse revised plan
            revised_plan = self.plan_parser.parse(response.content)
            if revised_plan:
                revised_plan.title = plan.title  # Keep original title
                self.plan_tracker.current_plan = revised_plan
                print("[Plan revised]")
                print(revised_plan.render())
            else:
                # Show LLM response if can't parse as plan
                print(response.content)
                print("\n[Could not parse as plan - showing response above]")

    def _handle_chat(self, user_input: str) -> None:
        """Handle natural language chat input."""
        # Check for plan commands when there's an active unconfirmed plan
        has_unconfirmed_plan = self.plan_tracker.has_active_plan() and not self.plan_tracker.is_plan_confirmed()
        if has_unconfirmed_plan:
            if self._handle_plan_command(user_input):
                return
            # Not a plan command - treat as conversation about the plan (no tools!)
            # This allows the AI to ask clarifying questions without executing

        # Check complexity for auto-planning (only if no pending plan)
        if not has_unconfirmed_plan and self.config.auto_plan_enabled:
            result = self.complexity.analyze(user_input)
            if result.should_plan and not self.mode_manager.is_plan:
                print(f"[Complex task detected (score: {result.score:.2f})]")
                print("[Entering PLAN mode]")
                self.mode_manager.to_plan()

        # Add to history
        self.history.append(Message(role="user", content=user_input))

        # Get tools for LLM (only in BUILD mode AND no pending plan)
        # When there's a pending plan, AI should converse without executing
        tools = None
        if self.mode_manager.is_build and not has_unconfirmed_plan:
            tools = self.registry.get_anthropic_tools()

        # Send to LLM with streaming (if available)
        llm_call = CancellableLLMCall()
        try:
            # Use streaming if provider supports it (no spinner - streaming is the feedback)
            if hasattr(self.llm, 'chat_stream'):
                response = llm_call.run(
                    self.llm.chat_stream,
                    messages=self.history,
                    tools=tools,
                    system=self._get_system_prompt(),
                )
                print()  # Newline after streaming
            else:
                # Non-streaming: use spinner
                spinner = Spinner("Thinking")
                spinner.start()
                try:
                    response = llm_call.run(
                        self.llm.chat,
                        messages=self.history,
                        tools=tools,
                        system=self._get_system_prompt(),
                    )
                finally:
                    spinner.stop()
        except KeyboardInterrupt:
            print("\n[Cancelled by user]")
            return

        # Check if response contains a plan
        if self.mode_manager.is_plan:
            if response.content:
                self.history.append(Message(role="assistant", content=response.content))
            plan = self.plan_parser.parse(response.content)
            if plan:
                self.plan_tracker.current_plan = plan
                print(plan.render())
                return
            elif response.content:
                print(response.content)
            return

        # Tool call loop - keep going until LLM is done with tool calls
        max_iterations = 20  # Safety limit
        iteration = 0
        accumulated_rounds = []  # Track all tool rounds for context

        while response.has_tool_calls and self.mode_manager.is_build and iteration < max_iterations:
            iteration += 1

            # Print any text content before tool calls
            if response.content:
                print(response.content)

            # Execute tool calls and collect results
            tool_results = self._execute_tool_calls_with_results(response)

            # If all tools were denied, stop
            if not tool_results:
                break

            # Accumulate this round
            accumulated_rounds.append({
                "content": response.content,
                "tool_calls": response.tool_calls,
                "results": tool_results,
            })

            # Continue conversation with ALL accumulated tool results (streaming)
            llm_call = CancellableLLMCall()
            try:
                if hasattr(self.llm, 'continue_with_tool_results_stream'):
                    response = llm_call.run(
                        self.llm.continue_with_tool_results_stream,
                        messages=self.history,
                        tool_rounds=accumulated_rounds,
                        tools=tools,
                        system=self._get_system_prompt(),
                    )
                    print()  # Newline after streaming
                else:
                    spinner = Spinner("Continuing")
                    spinner.start()
                    try:
                        response = llm_call.run(
                            self.llm.continue_with_tool_results,
                            messages=self.history,
                            tool_rounds=accumulated_rounds,
                            tools=tools,
                            system=self._get_system_prompt(),
                        )
                    finally:
                        spinner.stop()
            except KeyboardInterrupt:
                print("\n[Cancelled by user]")
                return

        # Add final response to history (already printed via streaming)
        if response.content:
            self.history.append(Message(role="assistant", content=response.content))

    def _execute_tool_calls_with_results(self, response: LLMResponse) -> list[ToolResult]:
        """Execute tool calls and return results for continuation.

        Returns:
            List of ToolResult objects, or empty list if all denied.
        """
        results = []

        for tool_call in response.tool_calls:
            tool_name = tool_call.name
            args = tool_call.arguments

            try:
                tool = self.registry.get(tool_name)

                # Check permission for non-read tools
                if tool.requires_build_mode:
                    # Auto-execute safe bash commands
                    is_safe = False
                    if tool_name == "bash" and "command" in args:
                        is_safe = self.config.is_safe_command(args["command"])

                    if not (is_safe and self.config.auto_execute_safe):
                        desc = _format_tool_description(tool_name, args)
                        try:
                            self.permission_gate.check(tool_name, desc)
                        except PermissionDenied as e:
                            print(red(f"[Denied] {e}"))
                            results.append(ToolResult(
                                tool_id=tool_call.id,
                                content=f"Permission denied: {e}. IMPORTANT: Do NOT output the code/content you were trying to write. Just acknowledge briefly and ask what to do next.",
                                is_error=True
                            ))
                            continue
                        except FeedbackProvided as e:
                            print(cyan(f"[Feedback] {e.feedback}"))
                            results.append(ToolResult(
                                tool_id=tool_call.id,
                                content=f"USER FEEDBACK - Do this instead: {e.feedback}",
                                is_error=True
                            ))
                            continue

                result = tool.execute(**args)

                if result.success:
                    # Show output
                    if result.output:
                        print(result.output)
                    # Use llm_output for LLM (may be full content vs truncated display)
                    results.append(ToolResult(
                        tool_id=tool_call.id,
                        content=result.llm_output or "Success",
                        is_error=False
                    ))
                else:
                    print(red(f"[Error] {result.error}"))
                    if result.output:
                        print(result.output)
                    results.append(ToolResult(
                        tool_id=tool_call.id,
                        content=f"Error: {result.error}\n{result.llm_output or ''}",
                        is_error=True
                    ))

            except KeyError:
                print(f"[Error] Unknown tool: {tool_name}")
                results.append(ToolResult(
                    tool_id=tool_call.id,
                    content=f"Unknown tool: {tool_name}",
                    is_error=True
                ))
            except Exception as e:
                print(f"[Error] {e}")
                results.append(ToolResult(
                    tool_id=tool_call.id,
                    content=f"Error: {e}",
                    is_error=True
                ))

        return results

    def _confirm_and_execute_plan(self) -> None:
        """Confirm and execute the current plan."""
        if not self.plan_tracker.confirm_plan():
            print("No plan to execute.")
            return

        print("\n[Executing plan...]")
        self.mode_manager.to_build()
        plan = self.plan_tracker.current_plan
        print(plan.render())

        tools = self.registry.get_anthropic_tools()
        status_bar = StatusBar()

        # Execute each step (use while loop to support retry)
        i = 0
        while i < len(plan.tasks):
            task = plan.tasks[i]
            plan.mark_in_progress(i)
            status_bar.update(plan)
            print(f"\n[Step {i + 1}] {task.description}")

            # Send step to LLM for execution
            step_msg = f"Execute step {i + 1}: {task.description}\n\nComplete this step fully - use all necessary tools (glob, read, write, edit, bash) to accomplish the task."
            self.history.append(Message(role="user", content=step_msg))

            llm_call = CancellableLLMCall()
            try:
                if hasattr(self.llm, 'chat_stream'):
                    response = llm_call.run(
                        self.llm.chat_stream,
                        messages=self.history,
                        tools=tools,
                        system=self._get_system_prompt(),
                    )
                    print()  # Newline after streaming
                else:
                    spinner = Spinner("Working")
                    spinner.start()
                    try:
                        response = llm_call.run(
                            self.llm.chat,
                            messages=self.history,
                            tools=tools,
                            system=self._get_system_prompt(),
                        )
                    finally:
                        spinner.stop()
            except KeyboardInterrupt:
                print("\n[Plan execution cancelled by user]")
                plan.mark_failed(i, "Cancelled by user")
                status_bar.update(plan)
                return

            # Tool call loop - continue until LLM is done with this step
            success = True
            max_iterations = 15
            iteration = 0
            accumulated_rounds = []  # Track all tool rounds for context

            while response.has_tool_calls and iteration < max_iterations:
                iteration += 1

                # Print any text content
                if response.content:
                    print(response.content)

                # Execute tool calls and collect results
                tool_results = self._execute_tool_calls_with_results(response)

                # Check for failures
                has_error = any(r.is_error for r in tool_results)
                if has_error and all(r.is_error for r in tool_results):
                    # All tools failed
                    success = False
                    error_msg = tool_results[0].content if tool_results else "Unknown error"
                    plan.mark_failed(i, error_msg)
                    print(f"[Step {i + 1}] FAILED: {error_msg}")
                    break

                # Accumulate this round
                accumulated_rounds.append({
                    "content": response.content,
                    "tool_calls": response.tool_calls,
                    "results": tool_results,
                })

                # Continue with ALL accumulated tool results (streaming)
                llm_call = CancellableLLMCall()
                try:
                    if hasattr(self.llm, 'continue_with_tool_results_stream'):
                        response = llm_call.run(
                            self.llm.continue_with_tool_results_stream,
                            messages=self.history,
                            tool_rounds=accumulated_rounds,
                            tools=tools,
                            system=self._get_system_prompt(),
                        )
                        print()  # Newline after streaming
                    else:
                        spinner = Spinner("Continuing")
                        spinner.start()
                        try:
                            response = llm_call.run(
                                self.llm.continue_with_tool_results,
                                messages=self.history,
                                tool_rounds=accumulated_rounds,
                                tools=tools,
                                system=self._get_system_prompt(),
                            )
                        finally:
                            spinner.stop()
                except KeyboardInterrupt:
                    print("\n[Plan execution cancelled by user]")
                    plan.mark_failed(i, "Cancelled by user")
                    status_bar.update(plan)
                    return

            # Add response to history (already printed via streaming)
            if response.content:
                self.history.append(Message(role="assistant", content=response.content))

            if success:
                plan.mark_done(i)
                print(f"[Step {i + 1}] Done.")
                i += 1
            else:
                # Step failed - ask user what to do
                status_bar.update(plan)
                print(f"\n[Step {i + 1} failed. What would you like to do?]")
                print("  [r]etry  [s]kip  [a]bort")
                try:
                    choice = input("  > ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    choice = "a"

                if choice in ("r", "retry"):
                    # Retry - don't increment i, just reset status
                    plan.tasks[i].status = TaskStatus.PENDING
                    # Continue without incrementing i
                elif choice in ("s", "skip"):
                    plan.mark_skipped(i)
                    print(f"[Step {i + 1}] Skipped.")
                    i += 1
                else:  # abort
                    print("[Plan aborted]")
                    return

            status_bar.update(plan)

        if plan.is_complete():
            status_bar.update(plan)
            print("\n[All steps completed]")
            self.plan_tracker.complete_plan()

    # --- Commands ---

    def _cmd_help(self, args: str) -> None:
        """Show help."""
        print("""
Commands:
  /help              Show this help
  /quit, /exit       Exit OpenCode-Py
  /clear             Clear chat history

Workspace:
  /init              Initialize workspace in current directory
  /workspace         Show workspace info

Mode:
  /plan              Switch to PLAN mode (read-only analysis)
  /build             Switch to BUILD mode (execution) or confirm plan
  /mode              Show current mode
  /auto              Enable auto-execution (no confirmations)
  /interactive       Disable auto-execution (default)

Session:
  /save [name]       Save current conversation
  /load <id>         Load a saved session
  /sessions          List all saved sessions
  /history           Alias for /sessions

Tools & Config:
  /tools             List available tools
  /sensitivity <N>   Set complexity threshold (0.0-1.0)
  /config            Show current configuration

Plan Commands (when a plan is shown):
  build              Execute the plan
  revise <feedback>  Ask AI to modify the plan
  add <N> <desc>     Add step at position N
  edit <N> <desc>    Edit step N description
  remove <N>         Remove step N
  cancel             Discard the plan

Usage:
  - Run 'opencode init' or /init to initialize workspace
  - File access is restricted to workspace directory
  - Type naturally to chat with the AI
  - Shell commands (ls, git status, etc.) are detected and executed
  - Complex tasks auto-enter PLAN mode
  - Sessions are saved to .opencode/sessions/

Examples:
  ls -la                     Run shell command
  refactor the auth module   Triggers PLAN mode
  /save my-feature           Save session as "my-feature"
  /sessions                  List saved sessions
  /load 20241224_143022      Load a session by ID
""")

    def _cmd_quit(self, args: str) -> None:
        """Exit the REPL."""
        raise EOFError()

    def _cmd_plan(self, args: str) -> None:
        """Switch to PLAN mode."""
        self.mode_manager.to_plan()

    def _cmd_build(self, args: str) -> None:
        """Switch to BUILD mode or confirm plan."""
        if self.plan_tracker.has_active_plan() and not self.plan_tracker.is_plan_confirmed():
            self._confirm_and_execute_plan()
        else:
            self.mode_manager.to_build()

    def _cmd_mode(self, args: str) -> None:
        """Show current mode."""
        print(f"Mode: {self.mode_manager.status()}")

    def _cmd_auto(self, args: str) -> None:
        """Enable auto-execution mode."""
        self.mode_manager.to_auto()

    def _cmd_interactive(self, args: str) -> None:
        """Disable auto-execution mode."""
        self.mode_manager.to_interactive()

    def _cmd_tools(self, args: str) -> None:
        """List available tools."""
        print("Available tools:")
        for tool in self.registry.all_tools():
            mode_note = " (BUILD mode)" if tool.requires_build_mode else ""
            print(f"  - {tool.name}: {tool.description}{mode_note}")

    def _cmd_sensitivity(self, args: str) -> None:
        """Set complexity threshold."""
        try:
            value = float(args.strip())
            self.complexity.set_threshold(value)
            print(f"Complexity threshold set to {value:.2f}")
        except ValueError:
            print(f"Current threshold: {self.complexity.threshold:.2f}")
            print("Usage: /sensitivity <0.0-1.0>")

    def _cmd_config(self, args: str) -> None:
        """Show current configuration."""
        import os

        print(f"LLM Provider: {self.config.llm_provider}")
        print(f"LLM Model: {self.config.llm_model}")
        print(f"API Key: {'***' if self.config.api_key else 'Not set'}")
        if self.config.base_url:
            print(f"Base URL: {self.config.base_url}")
        print(f"Complexity Threshold: {self.config.complexity_threshold}")
        print(f"Auto-Plan: {self.config.auto_plan_enabled}")
        print(f"Auto-Execute Safe: {self.config.auto_execute_safe}")

        # Show config file locations
        print("\n--- Config Files ---")
        global_path = Workspace.global_config_path()
        print(f"Global: {global_path} {'[exists]' if global_path.exists() else '[not found]'}")

        local_path = Path.cwd() / ".opencode" / "config.toml"
        print(f"Local:  {local_path} {'[exists]' if local_path.exists() else '[not found]'}")

        if self.workspace.is_initialized:
            ws_path = self.workspace.local_config_path
            if ws_path and ws_path != local_path:
                print(f"Workspace: {ws_path} {'[exists]' if ws_path.exists() else '[not found]'}")

        # Show relevant env vars
        print("\n--- Environment ---")
        for var in ["OPENCODE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
                    "OPENCODE_LLM_PROVIDER", "OPENCODE_LLM_MODEL"]:
            val = os.environ.get(var)
            if val:
                display = "***" if "KEY" in var else val
                print(f"{var}={display}")

    def _cmd_clear(self, args: str) -> None:
        """Clear chat history."""
        self.history.clear()
        self.plan_tracker.current_plan = None
        print("Chat history cleared.")

    def _cmd_init(self, args: str) -> None:
        """Initialize workspace in current directory."""
        if self.workspace.is_initialized:
            print(f"Workspace already initialized at: {self.workspace.root}")
            return

        path = Path(args).resolve() if args else Path.cwd()
        self.workspace.init(path)

        # Reload config to pick up local config
        self.config = Config.load(workspace=self.workspace)

        # Update registry workspace
        self.registry._workspace = self.workspace

        print(f"Workspace initialized at: {self.workspace.root}")
        print(f"Created:")
        print(f"  .opencode/")
        print(f"    - config.toml (local config)")
        print(f"    - workspace.json")
        print(green("  iai.md") + " (project instructions for AI)")
        print(f"\nEdit iai.md to tell the AI about your project.")
        print(f"File access: Can read/write all files inside this directory and subfolders.")

    def _cmd_workspace(self, args: str) -> None:
        """Show workspace info."""
        if self.workspace.is_initialized:
            print(f"Workspace: {self.workspace.root}")
            print(f"Config dir: {self.workspace.config_dir}")
            if self.workspace.local_config_path.exists():
                print(f"Local config: {self.workspace.local_config_path}")
        else:
            print("Workspace: Not initialized")
            print("Run /init or 'opencode init' to initialize")

        print(f"\nGlobal config: {Workspace.global_config_path()}")

    def _cmd_save(self, args: str) -> None:
        """Save current session."""
        if not self.history:
            print("No conversation to save.")
            return

        name = args.strip() if args else None
        try:
            session_id = self.session_manager.save(
                messages=self.history,
                name=name,
                session_id=self.current_session_id,
            )
            self.current_session_id = session_id
            print(f"Session saved: {session_id}")
            if name:
                print(f"Name: {name}")
        except Exception as e:
            print(f"Error saving session: {e}")

    def _cmd_load(self, args: str) -> None:
        """Load a saved session."""
        session_id = args.strip() if args else None

        if not session_id:
            # Load latest session
            session_id = self.session_manager.get_latest()
            if not session_id:
                print("No saved sessions found.")
                return
            print(f"Loading latest session: {session_id}")

        try:
            messages, metadata = self.session_manager.load(session_id)
            self.history = messages
            self.current_session_id = session_id
            print(f"Loaded session: {metadata.name}")
            print(f"Messages: {metadata.message_count}")
            if metadata.summary:
                print(f"Summary: {metadata.summary}")
        except FileNotFoundError:
            print(f"Session not found: {session_id}")
        except Exception as e:
            print(f"Error loading session: {e}")

    def _cmd_history(self, args: str) -> None:
        """Show conversation history."""
        if not self.history:
            print("No conversation history.")
            return

        # Parse limit from args
        limit = 10
        if args:
            try:
                limit = int(args.strip())
            except ValueError:
                pass

        print(f"Conversation history (last {min(limit, len(self.history))} messages):\n")

        for msg in self.history[-limit:]:
            role = msg.role.upper()
            content = msg.content[:200]
            if len(msg.content) > 200:
                content += "..."
            print(f"[{role}]")
            print(f"  {content}")
            print()

    def _cmd_sessions(self, args: str) -> None:
        """List saved sessions."""
        sessions = self.session_manager.list_sessions(limit=20)
        output = format_session_list(sessions)
        print(output)

        if sessions:
            print("Use /load <session_id> to load a session")


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """OpenCode-Py: A local-first coding agent CLI."""
    if ctx.invoked_subcommand is None:
        # Default to running the REPL
        ctx.invoke(run)


@cli.command("init")
@click.argument("path", required=False, type=click.Path())
def init_cmd(path):
    """Initialize a new workspace."""
    workspace = Workspace()

    if workspace.is_initialized:
        print(f"Workspace already initialized at: {workspace.root}")
        return

    target = Path(path).resolve() if path else Path.cwd()
    workspace.init(target)

    print(f"Workspace initialized at: {workspace.root}")
    print(f"Created:")
    print(f"  .opencode/")
    print(f"    - config.toml (local config)")
    print(f"    - workspace.json")
    print(green("  iai.md") + " (project instructions for AI)")
    print(f"\nEdit iai.md to tell the AI about your project.")
    print(f"File access: Can read/write all files inside this directory and subfolders.")
    print(f"Run 'opencode' to start.")


@cli.command("run")
@click.option(
    "--mode", "-m",
    type=click.Choice(["plan", "build"]),
    default="build",
    help="Initial operating mode"
)
@click.option(
    "--auto", "-a",
    is_flag=True,
    help="Enable auto-execution mode"
)
@click.option(
    "--provider", "-p",
    type=str,
    help="LLM provider: anthropic, openai, or custom"
)
@click.option(
    "--model",
    type=str,
    help="Model name (e.g., gpt-4o, claude-sonnet-4-20250514, llama3)"
)
@click.option(
    "--base-url",
    type=str,
    help="Base URL for custom OpenAI-compatible APIs"
)
def run(mode: str, auto: bool, provider: str, model: str, base_url: str):
    """Start the OpenCode-Py REPL."""
    # Ensure global config exists
    ensure_global_config()

    # Find or auto-init workspace
    workspace = Workspace()
    if not workspace.is_initialized:
        print(f"Initializing workspace in {Path.cwd()}...")
        workspace.init(Path.cwd())
        print(f"Created .opencode/ directory\n")

    # Load config (only uses local config from initialized workspace)
    config = Config.load(workspace=workspace)

    # CLI overrides
    if provider:
        config.llm_provider = provider
    if model:
        config.llm_model = model
    if base_url:
        config.base_url = base_url
        if config.llm_provider == "anthropic":
            config.llm_provider = "custom"

    repl = OpenCodeREPL(config=config, workspace=workspace)

    if mode == "plan":
        repl.mode_manager.to_plan()

    if auto:
        repl.mode_manager.to_auto()

    repl.run()


@cli.command("config")
@click.option("--global", "global_", is_flag=True, help="Edit global config")
def config_cmd(global_):
    """Show or edit configuration."""
    workspace = Workspace()

    if global_:
        config_path = Workspace.global_config_path()
    elif workspace.is_initialized and workspace.local_config_path:
        config_path = workspace.local_config_path
    else:
        config_path = Workspace.global_config_path()

    if config_path.exists():
        print(f"Config: {config_path}\n")
        print(config_path.read_text())
    else:
        print(f"Config not found: {config_path}")


def main():
    """Entry point for OpenCode-Py CLI."""
    cli()


if __name__ == "__main__":
    main()

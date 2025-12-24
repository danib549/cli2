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
from opencode.permissions import PermissionGate, Permission, PermissionDenied, FeedbackProvided, ExplorationRequired
from opencode.classifier import Classifier, InputType
from opencode.complexity import ComplexityAnalyzer
from opencode.tracker import PlanTracker, TaskStatus
from opencode.git import GitCheckpoint, create_checkpoint_fn
from opencode.session import SessionManager, format_session_list
from opencode.style import dim, bold, green, red, yellow, cyan, separator, ai_response_start, ai_response_end

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

REVIEW_MODE_INSTRUCTIONS = """# REVIEW Mode - Architectural Analysis

You are operating as a SENIOR PROGRAM ARCHITECT and TESTING ENGINEER.

================================================================================
                    COMPREHENSIVE CODE REVIEW PROTOCOL
================================================================================

Your mission: Provide the level of analysis a SENIOR ARCHITECT or TESTING
ENGINEER would expect. This is NOT a casual code review - this is a
comprehensive technical audit.

YOU MUST ANALYZE:

1. STRUCTURE & ORGANIZATION
   - File/module organization and naming
   - Package boundaries and dependencies
   - Separation of concerns
   - Code layering (presentation, business, data)

2. FUNCTION/CLASS SIGNATURES
   - Parameter types and validation
   - Return types and error handling
   - Method visibility (public/private)
   - Interface contracts

3. CODE FLOW & EXECUTION PATHS
   - Happy path analysis
   - Error/exception paths
   - Edge cases and boundary conditions
   - Async/concurrency patterns

4. DEPENDENCIES & COUPLING
   - Import analysis (internal/external)
   - Circular dependency detection
   - Loose vs tight coupling
   - Dependency injection patterns

5. TESTING CONSIDERATIONS
   - Testability assessment
   - Missing test coverage areas
   - Suggested test cases
   - Mocking requirements

6. SECURITY REVIEW
   - Input validation
   - Injection vulnerabilities
   - Authentication/authorization
   - Sensitive data handling

7. PERFORMANCE PATTERNS
   - N+1 query patterns
   - Memory usage concerns
   - Caching opportunities
   - Algorithmic complexity

8. CODE QUALITY
   - SOLID principles adherence
   - DRY violations
   - Complexity metrics
   - Documentation gaps

## Available Tools (READ-ONLY)
- `glob(pattern)` - Find files - MAP the structure
- `grep(pattern)` - Search for patterns - FIND connections
- `read(path)` - Read file contents - UNDERSTAND the code
- `tree(path, depth)` - Directory structure
- `outline(path)` - File structure
- `find_definition(symbol)` - Symbol definitions
- `find_references(symbol)` - Symbol usages
- NO: `write`, `edit`, `bash`, `rename_symbol`

## REVIEW METHODOLOGY
1. GLOB first - understand the full file structure
2. TREE - understand directory organization
3. GREP - find patterns, connections, usages
4. READ - deep dive into each relevant file
5. OUTLINE - understand file structures
6. ANALYZE - apply all 8 review dimensions
7. REPORT - structured findings with line references

## YOUR OUTPUT MUST INCLUDE
- Executive summary
- File-by-file analysis
- Dependency graph description
- Security findings (if any)
- Testing recommendations
- Prioritized action items

BE THOROUGH. BE CRITICAL. MISS NOTHING.
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

================================================================================
                    MANDATORY EXPLORATION PROTOCOL
================================================================================

STOP. Before you TOUCH any code, you MUST understand it first.

You are being monitored by an ExplorationGuard that WILL BLOCK your write/edit
operations if you have not properly explored the codebase first.

THE RULES (NON-NEGOTIABLE):
1. You CANNOT write or edit without first reading/exploring
2. You CANNOT modify a file you haven't read
3. You CANNOT create a new file without exploring the target directory
4. You MUST perform at least 2 exploration actions before ANY modification
5. If you try to skip exploration, your operation WILL BE DENIED

EXPLORATION SEQUENCE (FOLLOW THIS):
1. glob/tree first - understand the file structure
2. grep - find related code and patterns
3. read - understand the actual implementation
4. ONLY THEN - write or edit with confidence

================================================================================

## Tool Categories

### Discovery (ALWAYS USE FIRST)
- `glob(pattern)` - Find files: `glob("**/*.py")`, `glob("src/**/*.ts")`
- `grep(pattern)` - Search content: `grep("def login")`, `grep("TODO", output_mode="count")`
- `tree(path, depth)` - Directory structure: `tree("src", depth=2)`

### Code Navigation (USE TO UNDERSTAND)
- `find_definition(symbol)` - Where is it defined: `find_definition("UserService")`
- `find_references(symbol)` - Where is it used: `find_references("authenticate")`
- `find_symbols(query)` - Search symbols: `find_symbols("*Handler")`
- `outline(path)` - File structure: `outline("src/auth.py")`

### Read & Write (REQUIRES EXPLORATION FIRST)
- `read(path)` - Read file content - MANDATORY before edit
- `write(path, content)` - Create or overwrite file (BLOCKED until exploration done)
- `edit(path, old, new)` - Replace specific text (BLOCKED until you've read the file)

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

    def _can_stream(self) -> bool:
        """Check if streaming is enabled and available."""
        return self.config.stream and hasattr(self.llm, 'chat_stream')

    def _can_stream_continue(self) -> bool:
        """Check if streaming continuation is enabled and available."""
        return self.config.stream and hasattr(self.llm, 'continue_with_tool_results_stream')

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
        elif self.mode_manager.is_review:
            mode_instructions = REVIEW_MODE_INSTRUCTIONS
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
        print("(Multi-line paste supported - just paste, all lines will be captured)")
        print()

        while True:
            try:
                user_input = self._read_multiline_input()

                if not user_input:
                    continue

                self._handle_input(user_input)

            except KeyboardInterrupt:
                print("\n[Use /quit to exit]")
            except EOFError:
                break

        print("\nGoodbye.")

    def _read_multiline_input(self) -> str:
        """Read input, detecting multi-line paste.

        Works on both Windows and Unix. Detects when multiple lines
        are pasted by checking for pending input after each line.

        Returns:
            Combined input string (may be multiple lines).
        """
        import sys
        import os

        # Read first line with prompt
        first_line = input(self._get_prompt())

        # Check if there's more input waiting (paste detection)
        lines = [first_line]

        try:
            if os.name == 'nt':
                # Windows: use msvcrt
                import msvcrt
                import time

                # Give a tiny bit of time for paste buffer
                time.sleep(0.05)

                # Read all pending input
                while msvcrt.kbhit():
                    # Read a full line
                    try:
                        line = input()
                        lines.append(line)
                        time.sleep(0.02)  # Small delay to check for more
                    except EOFError:
                        break
            else:
                # Unix: use select
                import select

                # Check if more input is available with short timeout
                while True:
                    # Check if stdin has data waiting
                    readable, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if readable:
                        try:
                            line = sys.stdin.readline()
                            if line:
                                lines.append(line.rstrip('\n'))
                            else:
                                break
                        except EOFError:
                            break
                    else:
                        break

        except Exception:
            # If detection fails, just use the first line
            pass

        # Combine lines
        result = '\n'.join(lines)

        # If multi-line, show summary
        if len(lines) > 1:
            total_chars = len(result)
            print(f"[Captured {len(lines)} lines, {total_chars} chars]")

            # If very large, show preview
            if len(lines) > 20:
                preview = '\n'.join(lines[:3])
                print(f"Preview:\n{preview}\n...")

        return result.strip()

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
            "review": self._cmd_review,
            "mode": self._cmd_mode,
            "auto": self._cmd_auto,
            "interactive": self._cmd_interactive,
            "tools": self._cmd_tools,
            "sensitivity": self._cmd_sensitivity,
            "config": self._cmd_config,
            "setup": self._cmd_setup,
            "debug": self._cmd_debug,
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

        print(ai_response_start())
        llm_call = CancellableLLMCall()
        try:
            if self._can_stream():
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
            print(ai_response_end())
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
        print(ai_response_end())

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
        # Skip for PLAN and REVIEW modes - they're already specialized analysis modes
        if not has_unconfirmed_plan and self.config.auto_plan_enabled:
            if not self.mode_manager.is_read_only:
                result = self.complexity.analyze(user_input)
                if result.should_plan:
                    print(f"[Complex task detected (score: {result.score:.2f})]")
                    print("[Entering PLAN mode]")
                    self.mode_manager.to_plan()

        # Add to history
        self.history.append(Message(role="user", content=user_input))

        # Get tools for LLM based on mode
        # - BUILD mode: all tools (unless there's a pending plan)
        # - PLAN/REVIEW mode: read-only tools only
        # - Pending plan: no tools (AI should converse without executing)
        tools = None
        if has_unconfirmed_plan:
            tools = None  # No tools when there's a pending plan
        elif self.mode_manager.is_build:
            tools = self.registry.get_anthropic_tools()
        elif self.mode_manager.is_read_only:  # PLAN or REVIEW mode
            tools = self.registry.get_anthropic_tools(read_only=True)

        # Send to LLM with streaming (if available)
        print(ai_response_start())  # Visual marker for AI response
        llm_call = CancellableLLMCall()
        try:
            # Use streaming if provider supports it (no spinner - streaming is the feedback)
            if self._can_stream():
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
            print(ai_response_end())
            return

        # Check if response contains a plan
        if self.mode_manager.is_plan:
            if response.content:
                self.history.append(Message(role="assistant", content=response.content))
            plan = self.plan_parser.parse(response.content)
            if plan:
                self.plan_tracker.current_plan = plan
                print(plan.render())
                print(ai_response_end())
                return
            elif response.content:
                print(response.content)
            print(ai_response_end())
            return

        # Tool call loop - keep going until LLM is done with tool calls
        max_iterations = 20  # Safety limit
        iteration = 0
        accumulated_rounds = []  # Track all tool rounds for context

        # Allow tool calls in BUILD mode (all tools) or read-only modes (read-only tools)
        can_use_tools = self.mode_manager.is_build or self.mode_manager.is_read_only
        while response.has_tool_calls and can_use_tools and iteration < max_iterations:
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
                if self._can_stream_continue():
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

        print(ai_response_end())  # Visual marker for end of AI response

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
                            # Use exploration-aware permission check
                            self.permission_gate.check_with_exploration(
                                tool_name, args, desc
                            )
                        except ExplorationRequired as e:
                            # Exploration requirements not met - aggressive teacher mode
                            print(yellow(f"[EXPLORATION REQUIRED]"))
                            print(yellow(e.violation.teaching_message))
                            results.append(ToolResult(
                                tool_id=tool_call.id,
                                content=e.violation.teaching_message,
                                is_error=True
                            ))
                            continue
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

                # Always record tool execution for exploration tracking
                # This happens for ALL tools (read, glob, grep, write, edit, etc.)
                self.permission_gate.record_tool_execution(tool_name, args)

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
                if self._can_stream():
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
                    if self._can_stream_continue():
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
        # Check for specific help topics
        topic = args.strip().lower() if args else ""

        if topic == "config":
            self._help_config()
        elif topic in ("tools", "files"):
            self._help_tools()
        elif topic == "api":
            self._help_api()
        else:
            self._help_main()

    def _help_main(self) -> None:
        """Show main help."""
        print("""
OpenCode-Py - AI Coding Assistant
==================================

Commands:
  /help              Show this help
  /help config       Configuration help
  /help tools        Tools and file format help
  /help api          API key setup help
  /quit, /exit       Exit OpenCode-Py
  /clear             Clear chat history

Workspace:
  /init              Initialize workspace in current directory
  /workspace         Show workspace info

Mode:
  /plan              Switch to PLAN mode (read-only analysis)
  /build             Switch to BUILD mode (execution) or confirm plan
  /review [target]   Switch to REVIEW mode (architectural analysis)
  /review all        Full project analysis with graphs, flows, protocols
  /review phases     Show/edit review phases configuration
  /mode              Show current mode
  /auto              Enable auto-execution (no confirmations)
  /interactive       Disable auto-execution (default)

Session:
  /save [name]       Save current conversation
  /load <id>         Load a saved session
  /sessions          List all saved sessions
  /history           Alias for /sessions

Configuration:
  /config            Show current configuration
  /setup             Interactive configuration wizard
  /sensitivity <N>   Set complexity threshold (0.0-1.0)
  /debug             Toggle debug mode

Tools:
  /tools             List available tools

Plan Commands (when a plan is shown):
  build              Execute the plan
  revise <feedback>  Ask AI to modify the plan
  add <N> <desc>     Add step at position N
  edit <N> <desc>    Edit step N description
  remove <N>         Remove step N
  cancel             Discard the plan

Quick Start:
  1. Set your API key (see /help api)
  2. Run 'opencode init' or /init to initialize workspace
  3. Type naturally to chat with the AI

Examples:
  ls -la                     Run shell command
  read data.xlsx             Read Excel file
  read report.docx           Read Word document
  refactor the auth module   Triggers PLAN mode
  /save my-feature           Save session as "my-feature"
""")

    def _help_config(self) -> None:
        """Show configuration help."""
        from opencode.config import Config
        config_path = Config.get_global_config_path()
        print(f"""
Configuration
=============

Config File Locations:
  Global (Linux/Mac): ~/.opencode/config.toml
  Global (Windows):   %APPDATA%\\opencode\\config.toml
  Local (workspace):  .opencode/config.toml

Your global config: {config_path}

Configuration Priority (highest to lowest):
  1. Environment variables
  2. Local config (.opencode/config.toml)
  3. Global config (~/.opencode/config.toml)
  4. Default values

Environment Variables:
  ANTHROPIC_API_KEY       Anthropic API key
  OPENAI_API_KEY          OpenAI API key
  OPENCODE_API_KEY        Generic API key (overrides above)
  OPENCODE_LLM_PROVIDER   Provider: anthropic, openai, custom
  OPENCODE_LLM_MODEL      Model name
  OPENCODE_BASE_URL       Custom API endpoint
  OPENCODE_DEBUG          Enable debug mode (1/true)
  OPENCODE_SSL_CERT_PATH  Path to SSL certificate
  SSL_CERT_FILE           Standard SSL cert path
  REQUESTS_CA_BUNDLE      Alternative SSL cert path

Example config.toml:
  [llm]
  provider = "anthropic"
  model = "claude-sonnet-4-20250514"
  # api_key = "sk-..."  # Better to use env var

  [ssl]
  cert_path = "/path/to/ca-bundle.crt"
  verify = true

  [complexity]
  threshold = 0.6
  auto_plan = true

  [execution]
  auto_execute_safe = true
  tool_timeout = 30
  checkpoint_enabled = true

Commands:
  /config    Show current configuration
  /setup     Run interactive setup wizard
""")

    def _help_tools(self) -> None:
        """Show tools help."""
        print("""
Tools & File Formats
====================

Available Tools:
  read       Read files (text, code, Excel, Word, CSV)
  write      Write/create files
  edit       Edit files with find/replace
  bash       Execute shell commands
  glob       Find files by pattern
  grep       Search file contents
  outline    Show code structure

Supported File Formats:

  Text/Code Files:
    - All text files (.py, .js, .ts, .go, .rs, .java, etc.)
    - Automatic syntax detection
    - Large file handling with outline + preview

  Excel Files (.xlsx, .xls):
    - Requires: pip install openpyxl
    - Legacy .xls requires: pip install xlrd
    - Usage: read("data.xlsx")
    - Specify sheet: read("data.xlsx", sheet="Sales")

  Word Documents (.docx):
    - Requires: pip install python-docx
    - Extracts: paragraphs, headings, tables
    - Usage: read("report.docx")

  CSV Files (.csv):
    - Built-in support, no dependencies
    - Usage: read("data.csv")

Install All Optional Dependencies:
  pip install openpyxl xlrd python-docx

Tool Parameters:
  read(path, lines="10-20", full=True, sheet="Sheet1")
  write(path, content)
  edit(path, old_string, new_string)
  bash(command, timeout=30)
  glob(pattern, path=".")
  grep(pattern, path=".", type="py")

Examples:
  read("src/main.py")              Read Python file
  read("data.xlsx", sheet="Q4")    Read specific Excel sheet
  read("report.docx")              Read Word document
  read("large.py", lines="1-50")   Read specific lines
  read("big.py", full=True)        Read entire large file
""")

    def _help_api(self) -> None:
        """Show API key setup help."""
        import os
        from opencode.config import Config

        print("""
API Key Setup
=============

1. Get your API key:
   Anthropic: https://console.anthropic.com/settings/keys
   OpenAI:    https://platform.openai.com/api-keys

2. Set your API key:
""")
        if os.name == 'nt':
            print("""   WINDOWS (Command Prompt - temporary):
   set ANTHROPIC_API_KEY=sk-ant-your-key-here

   WINDOWS (PowerShell - temporary):
   $env:ANTHROPIC_API_KEY="sk-ant-your-key-here"

   WINDOWS (permanent):
   setx ANTHROPIC_API_KEY "sk-ant-your-key-here"
""")
        else:
            print("""   LINUX/MAC (temporary):
   export ANTHROPIC_API_KEY=sk-ant-your-key-here

   LINUX/MAC (permanent - add to ~/.bashrc or ~/.zshrc):
   echo 'export ANTHROPIC_API_KEY=sk-ant-your-key-here' >> ~/.bashrc
   source ~/.bashrc
""")

        print(f"""
3. Or store in config file (less secure):
   Edit: {Config.get_global_config_path()}
   Add under [llm]:
   api_key = "sk-ant-your-key-here"

4. Verify it's set:""")
        if os.name == 'nt':
            print("   echo %ANTHROPIC_API_KEY%")
        else:
            print("   echo $ANTHROPIC_API_KEY")

        print("""
For OpenAI, replace ANTHROPIC_API_KEY with OPENAI_API_KEY.

Quick Commands:
  /config    Show if API key is configured
  /setup     Run interactive setup wizard
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

    def _cmd_review(self, args: str) -> None:
        """Switch to REVIEW mode for architectural analysis."""
        self.mode_manager.to_review()
        print(yellow("REVIEW mode activated - read-only architectural analysis"))
        print("Use glob, grep, read, tree, outline to explore")
        print("NO writes or execution allowed")

        # If args provided, start a review
        if args.strip():
            target = args.strip()

            # Check for "all" mode - comprehensive full-project analysis
            if target.lower() == "all":
                print(yellow("Starting FULL PROJECT analysis (this may take a while)..."))
                self._run_review_all()
                return
            # Check for "phases" - show/edit phases config
            elif target.lower() == "phases":
                self._cmd_review_phases()
                return
            else:
                review_prompt = f"""Perform a comprehensive architectural review of: {target}

Analyze:
1. File structure and organization
2. All function/class signatures with parameters
3. Code flow and execution paths
4. Import dependencies and coupling
5. Security considerations
6. Testing gaps and recommendations
7. Performance patterns
8. Code quality issues

Provide a detailed report suitable for a senior architect."""
            self._handle_chat(review_prompt)

    def _get_review_phases_path(self) -> Path:
        """Get the path to the review phases config file."""
        if os.name == 'nt':  # Windows
            appdata = os.environ.get('APPDATA')
            if appdata:
                return Path(appdata) / "opencode" / "review_phases.toml"
        return Path.home() / ".opencode" / "review_phases.toml"

    def _load_review_phases_from_file(self) -> list[tuple[str, str]] | None:
        """Load review phases from user config file.

        Returns:
            List of (phase_name, prompt) tuples, or None if file doesn't exist.
        """
        phases_path = self._get_review_phases_path()
        if not phases_path.exists():
            return None

        try:
            import sys
            if sys.version_info >= (3, 11):
                import tomllib as tomli
            else:
                import tomli

            with open(phases_path, "rb") as f:
                data = tomli.load(f)

            phases = []
            # Phases are stored as [[phases]] array
            for phase in data.get("phases", []):
                name = phase.get("name", "Unnamed")
                prompt = phase.get("prompt", "")
                if prompt:
                    phases.append((name, prompt))

            if phases:
                return phases

        except Exception as e:
            print(yellow(f"Warning: Could not load {phases_path}: {e}"))
            print("Using default phases.")

        return None

    def _save_default_review_phases(self) -> Path:
        """Save default review phases to config file for user editing."""
        phases_path = self._get_review_phases_path()
        phases_path.parent.mkdir(parents=True, exist_ok=True)

        content = '''# OpenCode Review Phases Configuration
# Edit these phases to customize /review all output
# Each [[phases]] block defines one review phase
#
# IMPORTANT: Prompts should be DIRECTIVE - they must force the LLM to:
# 1. Execute tools immediately (not plan)
# 2. Provide concrete output with file:line references
# 3. Not just describe what it will do

# Tool instructions are NOT appended automatically anymore
# Include explicit tool commands in each phase prompt

[[phases]]
name = "Project Mapping"
prompt = """EXECUTE NOW - Do not plan, do not describe what you will do. Start using tools immediately.

STEP 1: Run `tree(".", depth=3)` to see COMPLETE directory structure
STEP 2: Run `glob("**/*")` to find ALL files (source, docs, config, data, etc.)
STEP 3: Categorize ALL files by type:
   - Source code: .py, .js, .ts, .c, .cpp, .h, .go, .rs, .java, .rb, .php, etc.
   - Documentation: .md, .rst, .txt, README, CHANGELOG, etc.
   - Config: .json, .yaml, .yml, .toml, .ini, .env, .xml, etc.
   - Data: .csv, .sql, .db, etc.
   - Build: Makefile, CMakeLists.txt, package.json, Cargo.toml, etc.
STEP 4: For source files, run `grep` to find imports/includes

After running the tools, provide:

1. **File Structure Summary**
   - List all directories and their purposes
   - ALL file types found (not just source code)
   - Identify entry points (files with main(), CLI commands, etc.)

2. **Dependency Graph** (ASCII art)
   Show which modules import which:
   ```
   module_a --> module_b --> module_c
   ```

3. **External Dependencies**
   - List all external packages/libraries used
   - Note any circular dependencies

START EXECUTING TOOLS NOW. Keep running tools until thorough.
When finished, say "PHASE COMPLETE" and provide findings."""

[[phases]]
name = "Data & Control Flow"
prompt = """EXECUTE NOW - Use tools immediately to trace data flow.

STEP 1: Run `grep("(def |function |class )")` to find all functions/classes
STEP 2: Run `grep("(input|stdin|argv|request|read)")` to find input sources
STEP 3: Run `grep("(print|write|send|response|output)")` to find output sinks
STEP 4: Read the main entry point file(s) to understand control flow

After running tools, provide:

1. **Input Sources** (with file:line references)
   - CLI arguments, Environment variables, File reads, Network/API inputs

2. **Output Sinks** (with file:line references)
   - STDOUT/STDERR, File writes, Network sends, Database writes

3. **Control Flow Diagram** (ASCII)

4. **Error Handling Paths**

START EXECUTING TOOLS NOW. Keep running tools until thorough.
When finished, say "PHASE COMPLETE" and provide findings."""

[[phases]]
name = "Protocols & Interfaces"
prompt = """EXECUTE NOW - Search for protocols and interfaces.

STEP 1: Run `grep("(http|socket|grpc|websocket|api)", "-i")` for external protocols
STEP 2: Run `grep("(class |interface |abstract |protocol )")` for internal interfaces
STEP 3: Run `grep("(json|yaml|toml|xml|serialize)")` for serialization
STEP 4: Read files that define public APIs

After running tools, provide:

1. **External Protocols** (with file:line)
2. **Internal Interfaces** (with file:line)
3. **Data Formats**

START EXECUTING TOOLS NOW. Keep running tools until thorough.
When finished, say "PHASE COMPLETE" and provide findings."""

[[phases]]
name = "State Management"
prompt = """EXECUTE NOW - Find all state in the application.

STEP 1: Run `grep("(global |static |self\\\\.|this\\\\.|_[a-z]+ =)")` for state variables
STEP 2: Run `grep("(cache|session|state|context|singleton)")` for state patterns
STEP 3: Read files with significant state management

After running tools, provide:

1. **Global State** (with file:line)
2. **Instance State** (with file:line)
3. **State Transitions**

START EXECUTING TOOLS NOW. Keep running tools until thorough.
When finished, say "PHASE COMPLETE" and provide findings."""

[[phases]]
name = "Security Analysis"
prompt = """EXECUTE NOW - Perform security audit.

STEP 1: Run `grep("(password|secret|key|token|credential)", "-i")` for secrets
STEP 2: Run `grep("(exec|eval|system|shell|subprocess)")` for command injection risks
STEP 3: Run `grep("(sql|query|execute.*\\\\()")` for SQL injection risks
STEP 4: Run `grep("(\\\\.\\\\./|path.*join|open\\\\()")` for path traversal risks
STEP 5: Read files that handle user input or authentication

After running tools, provide:

1. **Hardcoded Secrets** (CRITICAL - with file:line)
2. **Injection Vulnerabilities** (with file:line)
3. **Path Traversal Risks** (with file:line)
4. **Authentication/Authorization**
5. **Trust Boundaries**

START EXECUTING TOOLS NOW. Keep running tools until thorough.
When finished, say "PHASE COMPLETE" and provide findings."""

[[phases]]
name = "Component Analysis"
prompt = """EXECUTE NOW - Analyze each major component.

STEP 1: List ALL files with `glob("**/*")` - include source, config, docs, data files
STEP 2: For each major module/file, run `outline(path)` to see structure
STEP 3: Run `grep` for imports based on language:
   - C/C++: `grep("#include")`
   - Python: `grep("import|from .* import")`
   - JS/TS: `grep("import|require")`
STEP 4: Read key files to understand their purpose

After running tools, for EACH major component provide:

**Component: [name]**
- **Purpose**: What it does
- **Files**: Which files (with line counts)
- **Public API**: Key functions/classes exported
- **Dependencies**: What it imports
- **Complexity**: Simple/Medium/Complex

List ALL components found. Do not skip any.

START EXECUTING TOOLS NOW. Keep running tools until thorough.
When finished, say "PHASE COMPLETE" and provide findings."""

[[phases]]
name = "Call Graphs"
prompt = """EXECUTE NOW - Map function call hierarchies.

STEP 1: Find entry points based on language:
   - C/C++: `grep("int main|void main")`
   - Python: `grep("def main|if __name__")`
   - JS/TS: `grep("function main|exports\\\\.")`
STEP 2: For each entry point, run `outline` then `read` to trace calls
STEP 3: Run `grep` for each major function to find where it's called

After running tools, provide:

1. **Entry Points** (with file:line)

2. **Call Tree** (ASCII art for each entry point)
   ```
   main() [cli.py:100]
   +-- parse_args() [cli.py:50]
   +-- load_config() [config.py:30]
   +-- run() [core.py:100]
   ```

3. **Critical Paths**

START EXECUTING TOOLS NOW. Keep running tools until thorough.
When finished, say "PHASE COMPLETE" and provide findings."""

[[phases]]
name = "Quality Metrics"
prompt = """EXECUTE NOW - Measure code quality.

STEP 1: List all files with `glob("**/*")` and categorize by type (source, docs, config, data)
STEP 2: For each major file, run `outline` to count functions/classes
STEP 3: Run `read` on largest files to assess complexity
STEP 4: Run `grep("(TODO|FIXME|HACK|XXX)")` for technical debt

After running tools, provide:

1. **Code Metrics** (table format)
2. **Design Patterns Found** (with file:line)
3. **Anti-Patterns/Code Smells**
4. **Documentation Coverage**
5. **Technical Debt** (TODO/FIXME count)

START EXECUTING TOOLS NOW. Keep running tools until thorough.
When finished, say "PHASE COMPLETE" and provide findings."""

[[phases]]
name = "Testing Analysis"
prompt = """EXECUTE NOW - Analyze test coverage.

STEP 1: Find test files based on language detected earlier:
   - Python: `glob("**/test*.py")` or `glob("**/*_test.py")`
   - C/C++: `glob("**/test*.c")` or `glob("**/tests/*.c")`
   - JS/TS: `glob("**/*.test.{js,ts}")` or `glob("**/*.spec.{js,ts}")`
STEP 2: Run `glob("**/tests/**")` or `glob("**/test/**")` for test directories
STEP 3: For each test file, run `outline` to see what's tested
STEP 4: Compare against source files to find gaps

After running tools, provide:

1. **Test Files Found**
2. **Coverage Map** (table: Source Module | Test File | Coverage)
3. **Testing Gaps** (CRITICAL)
4. **Test Quality**
5. **Recommended Tests**

START EXECUTING TOOLS NOW. Keep running tools until thorough.
When finished, say "PHASE COMPLETE" and provide findings."""

[[phases]]
name = "Executive Summary"
prompt = """Based on all the analysis done in previous phases, synthesize your findings.

DO NOT run tools for this phase. Instead, provide a comprehensive summary:

## Architecture Overview
One paragraph describing the overall system architecture.

## Key Components
List the 3-5 most important components and their roles.

## Strengths
- What the codebase does well

## Weaknesses
- Areas needing improvement

## Security Findings
- Critical issues (if any)

## Risk Assessment
| Risk | Severity | Location | Recommendation |
|------|----------|----------|----------------|

## Prioritized Action Items
1. **[Critical]** ...
2. **[High]** ...
3. **[Medium]** ...
4. **[Low]** ...

Be specific and actionable. Reference file:line where relevant."""
'''
        phases_path.write_text(content)
        return phases_path

    def _get_review_phases(self) -> list[tuple[str, str]]:
        """Get list of (phase_name, prompt) tuples for phased review.

        Loads from user config file if available, otherwise uses defaults.
        """
        # Try to load from user config
        user_phases = self._load_review_phases_from_file()
        if user_phases:
            # Load tool instructions from config
            phases_path = self._get_review_phases_path()
            tool_instructions = ""
            try:
                import sys
                if sys.version_info >= (3, 11):
                    import tomllib as tomli
                else:
                    import tomli
                with open(phases_path, "rb") as f:
                    data = tomli.load(f)
                tool_instructions = data.get("settings", {}).get("tool_instructions", "")
            except Exception:
                pass

            # Append tool instructions to each phase if configured
            if tool_instructions:
                return [(name, f"{prompt}\n{tool_instructions}") for name, prompt in user_phases]
            return user_phases

        # Default phases - CRITICAL: These prompts must force EXECUTION, not planning
        # The LLM must use tools immediately and provide concrete output

        return [
            ("Project Mapping", """EXECUTE NOW - Do not plan, do not describe what you will do. Start using tools immediately.

STEP 1: Run `tree(".", depth=3)` to see COMPLETE directory structure
STEP 2: Run `glob("**/*")` to find ALL files (source, docs, config, data, etc.)
STEP 3: Categorize ALL files by type:
   - Source code: .py, .js, .ts, .c, .cpp, .h, .go, .rs, .java, .rb, .php, etc.
   - Documentation: .md, .rst, .txt, README, CHANGELOG, etc.
   - Config: .json, .yaml, .yml, .toml, .ini, .env, .xml, etc.
   - Data: .csv, .sql, .db, etc.
   - Build: Makefile, CMakeLists.txt, package.json, Cargo.toml, etc.
STEP 4: For source files, run `grep` to find imports/includes

After running the tools, provide:

1. **File Structure Summary**
   - List all directories and their purposes
   - ALL file types found (not just source code)
   - Identify entry points (files with main(), CLI commands, etc.)

2. **Dependency Graph** (ASCII art)
   Show which modules import which:
   ```
   module_a --> module_b --> module_c
   ```

3. **External Dependencies**
   - List all external packages/libraries used
   - Note any circular dependencies

START EXECUTING TOOLS NOW. Keep running tools until you have thorough coverage.
When finished with this phase, say "PHASE COMPLETE" and provide your findings."""),

            ("Data & Control Flow", """EXECUTE NOW - Use tools immediately to trace data flow.

STEP 1: Run `grep("(def |function |class )")` to find all functions/classes
STEP 2: Run `grep("(input|stdin|argv|request|read)")` to find input sources
STEP 3: Run `grep("(print|write|send|response|output)")` to find output sinks
STEP 4: Read the main entry point file(s) to understand control flow

After running tools, provide:

1. **Input Sources** (with file:line references)
   - CLI arguments
   - Environment variables
   - File reads
   - Network/API inputs
   - User prompts

2. **Output Sinks** (with file:line references)
   - STDOUT/STDERR
   - File writes
   - Network sends
   - Database writes

3. **Control Flow Diagram** (ASCII)
   ```
   main() --> parse_args() --> run_command() --> output()
   ```

4. **Error Handling Paths**
   - How errors propagate
   - Where exceptions are caught

START EXECUTING TOOLS NOW. Keep running tools until you have thorough coverage.
When finished with this phase, say "PHASE COMPLETE" and provide your findings."""),

            ("Protocols & Interfaces", """EXECUTE NOW - Search for protocols and interfaces.

STEP 1: Run `grep("(http|socket|grpc|websocket|api)", "-i")` for external protocols
STEP 2: Run `grep("(class |interface |abstract |protocol )")` for internal interfaces
STEP 3: Run `grep("(json|yaml|toml|xml|serialize)")` for serialization
STEP 4: Read files that define public APIs

After running tools, provide:

1. **External Protocols** (with file:line)
   - HTTP/REST endpoints
   - WebSocket connections
   - Database connections
   - Message queues

2. **Internal Interfaces** (with file:line)
   - Abstract base classes
   - Interface definitions
   - Function signatures of public APIs

3. **Data Formats**
   - JSON schemas used
   - Config file formats
   - Binary protocols

START EXECUTING TOOLS NOW. Keep running tools until you have thorough coverage.
When finished with this phase, say "PHASE COMPLETE" and provide your findings."""),

            ("State Management", """EXECUTE NOW - Find all state in the application.

STEP 1: Run `grep("(global |static |self\\.|this\\.|_[a-z]+ =)")` for state variables
STEP 2: Run `grep("(cache|session|state|context|singleton)")` for state patterns
STEP 3: Read files with significant state management

After running tools, provide:

1. **Global State** (with file:line)
   - Module-level variables
   - Singletons
   - Caches

2. **Instance State** (with file:line)
   - Class attributes
   - Session objects
   - Context managers

3. **State Transitions**
   - What triggers state changes
   - State machine patterns (if any)

START EXECUTING TOOLS NOW. Keep running tools until you have thorough coverage.
When finished with this phase, say "PHASE COMPLETE" and provide your findings."""),

            ("Security Analysis", """EXECUTE NOW - Perform security audit.

STEP 1: Run `grep("(password|secret|key|token|credential)", "-i")` for secrets
STEP 2: Run `grep("(exec|eval|system|shell|subprocess)")` for command injection risks
STEP 3: Run `grep("(sql|query|execute.*\\()")` for SQL injection risks
STEP 4: Run `grep("(\\.\\./|path.*join|open\\()")` for path traversal risks
STEP 5: Read files that handle user input or authentication

After running tools, provide:

1. **Hardcoded Secrets** (CRITICAL - with file:line)
   - API keys, passwords, tokens in code

2. **Injection Vulnerabilities** (with file:line)
   - Command injection risks
   - SQL injection risks
   - XSS risks

3. **Path Traversal Risks** (with file:line)
   - Unsafe file path handling

4. **Authentication/Authorization**
   - How auth is implemented
   - Any bypass risks

5. **Trust Boundaries**
   - Where untrusted input enters
   - Where validation happens

START EXECUTING TOOLS NOW. Keep running tools until you have thorough coverage.
When finished with this phase, say "PHASE COMPLETE" and provide your findings."""),

            ("Component Analysis", """EXECUTE NOW - Analyze each major component.

STEP 1: List ALL files with `glob("**/*")` - include source, config, docs, data files
STEP 2: For each major module/file, run `outline(path)` to see structure
STEP 3: Run `grep` for imports based on language:
   - C/C++: `grep("#include")`
   - Python: `grep("import|from .* import")`
   - JS/TS: `grep("import|require")`
   - Go: `grep("import")`
   - Rust: `grep("use |mod ")`
STEP 4: Read key files to understand their purpose

After running tools, for EACH major component provide:

**Component: [name]**
- **Purpose**: What it does
- **Files**: Which files (with line counts)
- **Public API**: Key functions/classes exported
- **Dependencies**: What it imports
- **Complexity**: Simple/Medium/Complex

List ALL components found. Do not skip any.

START EXECUTING TOOLS NOW. Keep running tools until you have thorough coverage.
When finished with this phase, say "PHASE COMPLETE" and provide your findings."""),

            ("Call Graphs", """EXECUTE NOW - Map function call hierarchies.

STEP 1: Find entry points based on language:
   - C/C++: `grep("int main|void main")`
   - Python: `grep("def main|if __name__|@click|@app\\.")`
   - JS/TS: `grep("function main|exports\\.|module\\.exports")`
   - Go: `grep("func main")`
   - Rust: `grep("fn main")`
STEP 2: For each entry point, run `outline` then `read` to trace calls
STEP 3: Run `grep` for each major function to find where it's called

After running tools, provide:

1. **Entry Points**
   List all entry points (with file:line)

2. **Call Tree** (ASCII art for each entry point)
   ```
   main() [cli.py:100]
   ├── parse_args() [cli.py:50]
   │   └── validate() [utils.py:20]
   ├── load_config() [config.py:30]
   └── run() [core.py:100]
       ├── process() [core.py:150]
       └── output() [io.py:80]
   ```

3. **Critical Paths**
   - Most frequently executed paths
   - Performance-critical sections

START EXECUTING TOOLS NOW. Keep running tools until you have thorough coverage.
When finished with this phase, say "PHASE COMPLETE" and provide your findings."""),

            ("Quality Metrics", """EXECUTE NOW - Measure code quality.

STEP 1: List all files with `glob("**/*")` and categorize by type (source, docs, config, data)
STEP 2: For each major file, run `outline` to count functions/classes
STEP 3: Run `read` on largest files to assess complexity
STEP 4: Run `grep("(TODO|FIXME|HACK|XXX)")` for technical debt

After running tools, provide:

1. **Code Metrics**
   | File | Lines | Functions | Classes | Complexity |
   |------|-------|-----------|---------|------------|
   | ... | ... | ... | ... | Low/Med/High |

2. **Design Patterns Found**
   - Factory, Singleton, Observer, etc.
   - With file:line references

3. **Anti-Patterns/Code Smells**
   - God classes
   - Long methods (>50 lines)
   - Deep nesting (>4 levels)

4. **Documentation Coverage**
   - Files with/without docstrings
   - Type hint usage

5. **Technical Debt**
   - TODO/FIXME count and locations

START EXECUTING TOOLS NOW. Keep running tools until you have thorough coverage.
When finished with this phase, say "PHASE COMPLETE" and provide your findings."""),

            ("Testing Analysis", """EXECUTE NOW - Analyze test coverage.

STEP 1: Find test files based on language:
   - Python: `glob("**/test*.py")` or `glob("**/*_test.py")`
   - C/C++: `glob("**/test*.c")` or `glob("**/tests/*.c")`
   - JS/TS: `glob("**/*.test.{js,ts}")` or `glob("**/*.spec.{js,ts}")`
   - Go: `glob("**/*_test.go")`
   - Rust: look for `#[test]` in `*.rs` files
STEP 2: Run `glob("**/tests/**")` or `glob("**/test/**")` for test directories
STEP 3: For each test file, run `outline` to see what's tested
STEP 4: Compare against source files to find gaps

After running tools, provide:

1. **Test Files Found**
   List all test files with their targets

2. **Coverage Map**
   | Source Module | Test File | Coverage |
   |---------------|-----------|----------|
   | ... | ... | Has tests / No tests |

3. **Testing Gaps** (CRITICAL)
   - Modules without tests
   - Complex code without tests
   - Error paths without tests

4. **Test Quality**
   - Unit vs integration vs e2e
   - Mocking patterns used
   - Edge cases covered

5. **Recommended Tests**
   Specific test cases that should be added

START EXECUTING TOOLS NOW. Keep running tools until you have thorough coverage.
When finished with this phase, say "PHASE COMPLETE" and provide your findings."""),

            ("Executive Summary", """Based on all the analysis done in previous phases, synthesize your findings.

DO NOT run tools for this phase. Instead, provide a comprehensive summary:

## Architecture Overview
One paragraph describing the overall system architecture.

## Key Components
List the 3-5 most important components and their roles.

## Strengths
- What the codebase does well
- Good patterns observed
- Well-tested areas

## Weaknesses
- Areas needing improvement
- Technical debt
- Missing tests

## Security Findings
- Critical issues (if any)
- Medium/Low risks

## Risk Assessment
| Risk | Severity | Location | Recommendation |
|------|----------|----------|----------------|
| ... | Critical/High/Medium/Low | file:line | Fix by... |

## Prioritized Action Items
1. **[Critical]** ...
2. **[High]** ...
3. **[Medium]** ...
4. **[Low]** ...

Be specific and actionable. Reference file:line where relevant."""),
        ]

    def _run_review_all(self) -> None:
        """Run full project review in phases, each in a fresh conversation.

        Each phase continues iterating until:
        - LLM signals completion (no tool calls + completion indicators)
        - Max iterations reached (safety limit)
        - Context too large

        Output is saved to .opencode/review_YYYYMMDD_HHMMSS.md
        """
        from datetime import datetime

        phases = self._get_review_phases()
        total = len(phases)

        # Configuration
        max_iterations_per_phase = 10  # Safety limit
        max_history_messages = 50  # Context size limit

        # Create output file in .opencode directory
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if self.workspace.is_initialized:
            review_dir = self.workspace.config_dir
        else:
            review_dir = Path.cwd() / ".opencode"
        review_dir.mkdir(parents=True, exist_ok=True)
        review_file = review_dir / f"review_{timestamp}.md"

        # Start the review file
        review_content = []
        review_content.append(f"# Code Review Report")
        review_content.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        review_content.append(f"Directory: {Path.cwd()}")
        review_content.append("")
        review_content.append("=" * 70)
        review_content.append("")

        print(f"\nStarting {total}-phase comprehensive review...")
        print(f"Output will be saved to: {review_file}")
        print("Each phase continues until complete or limit reached.\n")
        print("=" * 70)

        for i, (phase_name, prompt) in enumerate(phases, 1):
            # Clear conversation history for fresh context each phase
            self.history.clear()

            print(f"\n[PHASE {i}/{total}] {phase_name}")
            print("-" * 70)

            # Add phase header to file
            review_content.append(f"# PHASE {i}/{total}: {phase_name}")
            review_content.append("-" * 70)
            review_content.append("")

            # Track messages before this phase
            msg_count_before = len(self.history)

            # Initial prompt for this phase
            self._handle_chat(prompt)

            # Capture assistant responses for file
            self._capture_responses_to_list(review_content, msg_count_before)

            # Continue phase until complete
            iteration = 1
            while iteration < max_iterations_per_phase:
                # Check if context is getting too large
                if len(self.history) >= max_history_messages:
                    print(dim(f"\n[Phase context limit reached ({len(self.history)} messages)]"))
                    review_content.append(f"\n[Phase context limit reached ({len(self.history)} messages)]")
                    break

                # Check if last response indicates completion
                if self._phase_appears_complete():
                    break

                # Continue the phase
                iteration += 1
                print(dim(f"\n[Continuing phase {i}, iteration {iteration}...]"))

                msg_count_before = len(self.history)
                continue_prompt = """Continue your analysis. If you have more tools to run, run them now.
If you've completed this phase, say "PHASE COMPLETE" and provide your final summary for this phase."""

                self._handle_chat(continue_prompt)

                # Capture new responses
                self._capture_responses_to_list(review_content, msg_count_before)

            if iteration >= max_iterations_per_phase:
                print(dim(f"\n[Phase iteration limit reached ({max_iterations_per_phase})]"))
                review_content.append(f"\n[Phase iteration limit reached ({max_iterations_per_phase})]")

            review_content.append("")
            review_content.append("=" * 70)
            review_content.append("")

            print("\n" + "=" * 70)

            # Save after each phase (in case of interruption)
            review_file.write_text("\n".join(review_content), encoding="utf-8")

        # Final save
        review_file.write_text("\n".join(review_content), encoding="utf-8")

        print("\nFull project review complete.")
        print(f"All {total} phases have been analyzed.")
        print(green(f"\nReview saved to: {review_file}"))

    def _capture_responses_to_list(self, content_list: list, from_index: int) -> None:
        """Capture assistant responses from history to a content list.

        Args:
            content_list: List to append content to.
            from_index: Start index in history to capture from.
        """
        for msg in self.history[from_index:]:
            if msg.role == "assistant" and msg.content:
                content_list.append(msg.content)
                content_list.append("")

    def _phase_appears_complete(self) -> bool:
        """Check if the current phase appears to be complete.

        Looks at the last assistant message for completion indicators.

        Returns:
            True if phase seems done, False if should continue.
        """
        if not self.history:
            return False

        # Find last assistant message
        last_assistant = None
        for msg in reversed(self.history):
            if msg.role == "assistant" and msg.content:
                last_assistant = msg.content.lower()
                break

        if not last_assistant:
            return False

        # Completion indicators
        completion_markers = [
            "phase complete",
            "analysis complete",
            "review complete",
            "completed the analysis",
            "finished analyzing",
            "that concludes",
            "in summary",
            "to summarize",
            "## summary",
            "## findings",
            "## conclusion",
            "prioritized action items",
            "action items:",
        ]

        for marker in completion_markers:
            if marker in last_assistant:
                return True

        # If the response is very short and no tool calls, probably waiting for more
        # But if it's long with structured output, probably done
        if len(last_assistant) > 1500:
            # Long response with headers likely means complete analysis
            if "##" in last_assistant or "**" in last_assistant:
                return True

        return False

    def _cmd_review_phases(self) -> None:
        """Show or create the review phases configuration file."""
        phases_path = self._get_review_phases_path()

        if phases_path.exists():
            # Show current phases
            print(f"Review phases config: {phases_path}\n")
            phases = self._get_review_phases()
            print(f"Current phases ({len(phases)}):")
            for i, (name, _) in enumerate(phases, 1):
                print(f"  {i}. {name}")
            print(f"\nEdit {phases_path} to customize phases.")
            print("Changes take effect on next /review all")
        else:
            # Offer to create
            print(f"No phases config found at: {phases_path}")
            print("\nCreate default phases config? [Y/n]: ", end="", flush=True)
            try:
                response = input().strip().lower()
                if response in ("", "y", "yes"):
                    path = self._save_default_review_phases()
                    print(green(f"\nCreated: {path}"))
                    print("\nEdit this file to customize review phases:")
                    print("  - Add/remove [[phases]] blocks")
                    print("  - Modify prompts for each phase")
                    print("  - Adjust [settings].tool_instructions")
                else:
                    print("Cancelled.")
            except EOFError:
                # Non-interactive mode
                path = self._save_default_review_phases()
                print(green(f"Created: {path}"))

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
        from opencode.config import Config

        print("Current Configuration")
        print("=" * 40)

        # LLM settings
        print("\n[LLM]")
        print(f"  Provider: {self.config.llm_provider}")
        print(f"  Model: {self.config.llm_model}")
        print(f"  API Key: {'configured' if self.config.api_key else 'NOT SET'}")
        if self.config.base_url:
            print(f"  Base URL: {self.config.base_url}")

        # SSL settings
        print("\n[SSL]")
        print(f"  Cert Path: {self.config.ssl_cert_path or '(system default)'}")
        print(f"  Verify: {self.config.ssl_verify}")

        # Behavior settings
        print("\n[Behavior]")
        print(f"  Complexity Threshold: {self.config.complexity_threshold}")
        print(f"  Auto-Plan: {self.config.auto_plan_enabled}")
        print(f"  Auto-Execute Safe: {self.config.auto_execute_safe}")
        print(f"  Debug Mode: {self.config.debug}")

        # Show config file locations
        print("\n[Config Files]")
        global_path = Config.get_global_config_path()
        print(f"  Global: {global_path}")
        print(f"          {'[exists]' if global_path.exists() else '[not found]'}")

        local_path = Path.cwd() / ".opencode" / "config.toml"
        print(f"  Local:  {local_path}")
        print(f"          {'[exists]' if local_path.exists() else '[not found]'}")

        # Show config source
        if hasattr(self.config, '_source'):
            print(f"\n[Active Source]")
            print(f"  Loaded from: {self.config._source.loaded_from}")
            if self.config._source.errors:
                print(f"  Errors: {', '.join(self.config._source.errors)}")

        # Show relevant env vars
        print("\n[Environment Variables]")
        env_vars = [
            "OPENCODE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY",
            "OPENCODE_LLM_PROVIDER", "OPENCODE_LLM_MODEL", "OPENCODE_BASE_URL",
            "OPENCODE_SSL_CERT_PATH", "SSL_CERT_FILE", "OPENCODE_DEBUG"
        ]
        found_any = False
        for var in env_vars:
            val = os.environ.get(var)
            if val:
                found_any = True
                display = "***" if "KEY" in var else val
                print(f"  {var}={display}")
        if not found_any:
            print("  (none set)")

        print("\nUse /help config for configuration help")
        print("Use /setup to run interactive setup")

    def _cmd_setup(self, args: str) -> None:
        """Run interactive configuration setup."""
        from opencode.config import Config

        print("Running configuration setup...\n")
        try:
            new_config = Config.setup_wizard()
            # Reload config
            self.config = new_config
            print("\nConfiguration updated. Use /config to view.")
        except KeyboardInterrupt:
            print("\nSetup cancelled.")
        except Exception as e:
            print(f"\nSetup failed: {e}")

    def _cmd_debug(self, args: str) -> None:
        """Toggle debug mode."""
        self.config.debug = not self.config.debug
        status = "enabled" if self.config.debug else "disabled"
        print(f"Debug mode {status}")

        if self.config.debug:
            print("  - LLM requests/responses will be logged")
            print("  - Config loading will show details")
            print("  - Additional diagnostic info will be shown")

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


# =============================================================================
# CLI Entry Point
# =============================================================================

HELP_EPILOG = """
\b
CONFIGURATION
=============

Config files (TOML format):
  Global:  ~/.opencode/config.toml (Linux/macOS)
           %APPDATA%/opencode/config.toml (Windows)
  Local:   .opencode/config.toml (per-project, overrides global)

Environment variables (override config files):
  ANTHROPIC_API_KEY     API key for Anthropic/Claude
  OPENAI_API_KEY        API key for OpenAI
  OPENCODE_API_KEY      Generic API key (highest priority)
  OPENCODE_LLM_PROVIDER Provider: anthropic, openai, or custom
  OPENCODE_LLM_MODEL    Model name
  OPENCODE_BASE_URL     Custom API endpoint URL

\b
Example config.toml:

  [llm]
  provider = "anthropic"          # or "openai", "custom"
  model = "claude-sonnet-4-20250514"
  # api_key = "sk-..."           # Better: use env vars
  # base_url = "http://localhost:11434/v1"  # For Ollama

  [complexity]
  threshold = 0.6                 # Auto-plan trigger (0.0-1.0)
  auto_plan = true                # Enable auto-planning

  [execution]
  auto_execute_safe = true        # Auto-run safe commands
  tool_timeout = 30               # Tool timeout in seconds

\b
MODES
=====

Operating modes (switch with /plan, /build, /review):
  PLAN    Read-only analysis and planning
  BUILD   Full execution with file edits and shell commands
  REVIEW  Deep architectural analysis (read-only)

Execution modes (switch with /auto, /interactive):
  INTERACTIVE  Ask before running commands (default)
  AUTO         Run commands without confirmation

\b
REVIEW PHASES
=============

Customize /review all phases:
  1. Run: opencode
  2. Type: /review phases
  3. Edit: ~/.opencode/review_phases.toml

\b
QUICK START
===========

1. Set your API key:
   export ANTHROPIC_API_KEY="sk-ant-..."

2. Start the agent:
   opencode

\b
MORE INFO
=========

In-app help:    /help
Project:        https://github.com/anthropics/opencode
"""


@click.group(invoke_without_command=True, epilog=HELP_EPILOG)
@click.option("--version", "-v", is_flag=True, help="Show version and exit")
@click.pass_context
def cli(ctx, version):
    """OpenCode-Py: AI-powered coding agent for software engineering.

    \b
    An intelligent CLI that helps you analyze, plan, and modify code.
    Runs locally with your choice of LLM provider (Anthropic, OpenAI,
    or any OpenAI-compatible API like Ollama or LM Studio).

    \b
    USAGE:
      opencode              Start the interactive REPL (default)
      opencode init [PATH]  Initialize workspace in directory
      opencode run [OPTS]   Start REPL with specific options
      opencode config       Show current configuration

    \b
    EXAMPLES:
      opencode                            # Start with defaults
      opencode run --mode plan            # Start in read-only mode
      opencode run --provider openai      # Use OpenAI
      opencode run --model gpt-4o         # Specify model
      opencode run -a                     # Auto-execute mode
      opencode run --base-url http://localhost:11434/v1  # Use Ollama

    \b
    FIRST TIME SETUP:
      1. Get an API key from https://console.anthropic.com
      2. export ANTHROPIC_API_KEY="sk-ant-..."
      3. opencode
    """
    if version:
        click.echo("OpenCode-Py v0.1.0")
        ctx.exit()

    if ctx.invoked_subcommand is None:
        # Default to running the REPL
        ctx.invoke(run)


@cli.command("init")
@click.argument("path", required=False, type=click.Path())
def init_cmd(path):
    """Initialize a new workspace.

    \b
    Creates a .opencode/ directory with:
      - config.toml    Local configuration (overrides global)
      - workspace.json Workspace metadata
      - iai.md         Project instructions for the AI

    \b
    The workspace restricts file access to the initialized directory
    and its subdirectories for safety.

    \b
    EXAMPLES:
      opencode init           # Initialize in current directory
      opencode init ./myproj  # Initialize in specific directory
    """
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
    """Start the OpenCode-Py interactive REPL.

    \b
    Launches the AI coding agent with an interactive chat interface.
    Command-line options override config file settings.

    \b
    MODES:
      --mode plan   Start in read-only mode (analysis only)
      --mode build  Start in execution mode (can modify files)

    \b
    PROVIDERS:
      anthropic  Claude models (default)
      openai     GPT models
      custom     Any OpenAI-compatible API (Ollama, LM Studio, etc.)

    \b
    EXAMPLES:
      opencode run                     # Default settings
      opencode run -m plan             # Read-only mode
      opencode run -a                  # Auto-execute commands
      opencode run -p openai           # Use OpenAI
      opencode run --model llama3 --base-url http://localhost:11434/v1

    \b
    INTERACTIVE COMMANDS (once running):
      /help      Show all commands
      /plan      Switch to plan mode
      /build     Switch to build mode
      /review    Switch to review mode
      /quit      Exit the REPL
    """
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
    """Show current configuration.

    \b
    Displays the contents of the active config file.
    By default, shows local config if in a workspace, otherwise global.

    \b
    CONFIG LOCATIONS:
      Global:  ~/.opencode/config.toml
      Local:   .opencode/config.toml (per-project)

    \b
    PRIORITY (highest to lowest):
      1. Environment variables (OPENCODE_*, ANTHROPIC_API_KEY, etc.)
      2. Local config (.opencode/config.toml)
      3. Global config (~/.opencode/config.toml)

    \b
    EXAMPLES:
      opencode config           # Show active config
      opencode config --global  # Show global config

    \b
    To edit, open the file in your editor:
      vim ~/.opencode/config.toml
    """
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

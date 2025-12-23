"""Abstract LLM interface."""

import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class Message:
    """A chat message."""
    role: str  # "user", "assistant", "system"
    content: str


@dataclass
class ToolCall:
    """A tool call from the LLM."""
    id: str
    name: str
    arguments: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Response from an LLM."""
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"

    @property
    def has_tool_calls(self) -> bool:
        """Check if response contains tool calls."""
        return len(self.tool_calls) > 0


@dataclass
class ToolResult:
    """Result from executing a tool."""
    tool_id: str
    content: str
    is_error: bool = False


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        tools: list[dict] = None,
        system: str = None,
    ) -> LLMResponse:
        """Send a chat request to the LLM.

        Args:
            messages: List of chat messages.
            tools: Optional list of tool schemas.
            system: Optional system prompt.

        Returns:
            LLMResponse with content and/or tool calls.
        """
        pass

    @abstractmethod
    def continue_with_tool_results(
        self,
        messages: list[Message],
        tool_rounds: list[dict],
        tools: list[dict] = None,
        system: str = None,
    ) -> LLMResponse:
        """Continue conversation after tool execution.

        Args:
            messages: Previous user/assistant messages (chat history).
            tool_rounds: List of tool interaction rounds, each containing:
                - "content": Assistant's text content (str)
                - "tool_calls": List of ToolCall objects
                - "results": List of ToolResult objects
            tools: Tool schemas (to allow more tool calls).
            system: System prompt.

        Returns:
            LLMResponse - may contain more tool calls or final response.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available (API key set, etc.)."""
        pass


class MockLLMProvider(LLMProvider):
    """Basic mock LLM provider for testing."""

    def __init__(self):
        self.responses: list[str] = []
        self.response_index = 0

    def add_response(self, response: str) -> None:
        """Add a canned response."""
        self.responses.append(response)

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] = None,
        system: str = None,
    ) -> LLMResponse:
        """Return a canned response or echo the last message."""
        if self.responses and self.response_index < len(self.responses):
            content = self.responses[self.response_index]
            self.response_index += 1
        else:
            last_user = next(
                (m.content for m in reversed(messages) if m.role == "user"),
                "No message"
            )
            content = f"[Mock] Received: {last_user}"

        return LLMResponse(content=content)

    def continue_with_tool_results(
        self,
        messages: list[Message],
        tool_rounds: list[dict],
        tools: list[dict] = None,
        system: str = None,
    ) -> LLMResponse:
        """Mock just returns a summary of results."""
        all_results = []
        for rnd in tool_rounds:
            for r in rnd.get("results", []):
                all_results.append(f"- {r.tool_id}: {r.content[:50]}...")
        summary = "\n".join(all_results)
        return LLMResponse(content=f"[Mock] Tool results received:\n{summary}")

    def is_available(self) -> bool:
        """Mock is always available."""
        return True


class SmartMockProvider(LLMProvider):
    """Smart mock LLM that understands common intents and generates tool calls."""

    # Intent patterns -> (response_template, tool_generator)
    # Order matters! More specific patterns should come first
    INTENTS = [
        # Git commands (must come before generic show/read)
        (r"(?:show|check|what(?:'s| is)?)\s+(?:the\s+)?git\s+status", "git_status"),
        (r"git\s+status", "git_status"),

        # Directory/pwd (must come before generic show)
        (r"(?:what(?:'s| is)?|show)\s+(?:the\s+)?(?:current\s+)?(?:directory|pwd|cwd|folder)", "show_pwd"),

        # Project structure
        (r"(?:check|show|what(?:'s| is)?)\s+(?:the\s+)?(?:project\s+)?(?:structure|tree)", "show_tree"),

        # List files (must come before generic show)
        (r"(?:list|ls)\s+(?:the\s+)?(?:files?)?(?:\s+(?:in|of)\s+)?([^\s]*)", "list_files"),
        (r"(?:show|what(?:'s| is| are)?)\s+(?:the\s+)?(?:files?|directory|folder|contents?)(?:\s+(?:in|of)\s+)?([^\s]*)", "list_files"),

        # File operations
        (r"(?:read|display|cat|view|open)\s+(?:the\s+)?(?:file\s+)?['\"]?([^\s'\"]+)['\"]?", "read_file"),
        (r"show\s+(?:me\s+)?(?:the\s+)?(?:file\s+)?['\"]?([^\s'\"]+\.\w+)['\"]?", "read_file"),

        # Edit operations
        (r"(?:edit|change|modify|update|replace)\s+['\"]?([^'\"]+)['\"]?\s+(?:in|from)\s+['\"]?([^\s'\"]+)['\"]?", "edit_file"),
        (r"(?:create|write|make)\s+(?:a\s+)?(?:new\s+)?(?:file\s+)?['\"]?([^\s'\"]+)['\"]?", "create_file"),

        # Shell/system
        (r"(?:run|execute|do)\s+['\"]?(.+)['\"]?", "run_command"),

        # Help/info
        (r"(?:help|what can you do|how do i|how to)", "show_help"),
        (r"(?:who|what)\s+are\s+you", "introduce"),
        (r"^(?:hello|hi|hey|greetings)(?:\s|$|!)", "greet"),
    ]

    def __init__(self):
        self._tool_id_counter = 0

    def _gen_tool_id(self) -> str:
        """Generate a unique tool ID."""
        self._tool_id_counter += 1
        return f"tool_{self._tool_id_counter}"

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] = None,
        system: str = None,
    ) -> LLMResponse:
        """Parse intent and generate smart response."""
        # Get last user message
        last_user = next(
            (m.content for m in reversed(messages) if m.role == "user"),
            ""
        )

        if not last_user:
            return LLMResponse(content="I didn't receive a message. How can I help?")

        # Check available tools
        available_tools = set()
        if tools:
            for tool in tools:
                name = tool.get("name", "")
                if name:
                    available_tools.add(name)

        # Try to match intent (order matters!)
        user_lower = last_user.lower().strip()

        for pattern, intent in self.INTENTS:
            match = re.search(pattern, user_lower, re.IGNORECASE)
            if match:
                return self._handle_intent(intent, match, available_tools, last_user)

        # No specific intent matched - provide helpful response
        return self._default_response(last_user, available_tools)

    def _handle_intent(
        self,
        intent: str,
        match: re.Match,
        available_tools: set,
        original: str
    ) -> LLMResponse:
        """Handle a matched intent."""

        if intent == "read_file":
            filepath = match.group(1)
            if "read" in available_tools:
                return LLMResponse(
                    content=f"I'll read the file `{filepath}` for you.",
                    tool_calls=[ToolCall(
                        id=self._gen_tool_id(),
                        name="read",
                        arguments={"path": filepath}
                    )]
                )
            return LLMResponse(content=f"I would read `{filepath}`, but read tool is not available.")

        elif intent == "list_files":
            try:
                directory = match.group(1).strip() if match.lastindex and match.group(1) else "."
            except IndexError:
                directory = "."
            if not directory:
                directory = "."
            if "bash" in available_tools:
                return LLMResponse(
                    content=f"I'll list the files in `{directory}`.",
                    tool_calls=[ToolCall(
                        id=self._gen_tool_id(),
                        name="bash",
                        arguments={"command": f"ls -la {directory}"}
                    )]
                )
            return LLMResponse(content="I would list files, but bash tool is not available.")

        elif intent == "show_tree":
            if "bash" in available_tools:
                return LLMResponse(
                    content="I'll show you the project structure.",
                    tool_calls=[ToolCall(
                        id=self._gen_tool_id(),
                        name="bash",
                        arguments={"command": "find . -type f -name '*.py' | head -20"}
                    )]
                )
            return LLMResponse(content="I would show the project tree, but bash tool is not available.")

        elif intent == "show_pwd":
            if "bash" in available_tools:
                return LLMResponse(
                    content="I'll show the current directory.",
                    tool_calls=[ToolCall(
                        id=self._gen_tool_id(),
                        name="bash",
                        arguments={"command": "pwd"}
                    )]
                )
            return LLMResponse(content=f"Current directory: {Path.cwd()}")

        elif intent == "git_status":
            if "bash" in available_tools:
                return LLMResponse(
                    content="I'll check the git status.",
                    tool_calls=[ToolCall(
                        id=self._gen_tool_id(),
                        name="bash",
                        arguments={"command": "git status"}
                    )]
                )
            return LLMResponse(content="I would check git status, but bash tool is not available.")

        elif intent == "run_command":
            command = match.group(1)
            if "bash" in available_tools:
                return LLMResponse(
                    content=f"I'll run: `{command}`",
                    tool_calls=[ToolCall(
                        id=self._gen_tool_id(),
                        name="bash",
                        arguments={"command": command}
                    )]
                )
            return LLMResponse(content="I would run that command, but bash tool is not available.")

        elif intent == "create_file":
            filepath = match.group(1)
            return LLMResponse(
                content=f"To create `{filepath}`, please tell me what content to put in it."
            )

        elif intent == "edit_file":
            what = match.group(1)
            filepath = match.group(2)
            return LLMResponse(
                content=f"To edit `{filepath}`, please specify:\n"
                        f"1. The exact text to find\n"
                        f"2. What to replace it with"
            )

        elif intent == "show_help":
            return LLMResponse(content=self._help_text())

        elif intent == "introduce":
            return LLMResponse(
                content="I'm OpenCode-Py, a local-first coding agent. "
                        "I can help you with:\n"
                        "- Reading and editing files\n"
                        "- Running shell commands\n"
                        "- Exploring your codebase\n"
                        "- Planning complex tasks\n\n"
                        "Try asking me to 'list files' or 'read <filename>'!"
            )

        elif intent == "greet":
            return LLMResponse(
                content="Hello! I'm OpenCode-Py, your coding assistant. "
                        "How can I help you today?\n\n"
                        "You can ask me to:\n"
                        "- List or read files\n"
                        "- Run commands\n"
                        "- Help with coding tasks"
            )

        return self._default_response(original, available_tools)

    def _default_response(self, user_input: str, available_tools: set) -> LLMResponse:
        """Generate a helpful default response."""
        # Check if it looks like a question about files
        if any(word in user_input.lower() for word in ["file", "code", "project", "directory"]):
            if "bash" in available_tools:
                return LLMResponse(
                    content="Let me help you explore the project. I'll list the files first.",
                    tool_calls=[ToolCall(
                        id=self._gen_tool_id(),
                        name="bash",
                        arguments={"command": "ls -la"}
                    )]
                )

        # General helpful response
        return LLMResponse(
            content=f"I understand you said: \"{user_input}\"\n\n"
                    "I can help you with:\n"
                    "- **Reading files**: 'read <filename>' or 'show me <filename>'\n"
                    "- **Listing files**: 'list files' or 'show directory'\n"
                    "- **Running commands**: 'run <command>'\n"
                    "- **Git status**: 'git status' or 'show status'\n\n"
                    "What would you like me to do?"
        )

    def _help_text(self) -> str:
        """Return help text."""
        return """I'm OpenCode-Py running in smart mock mode (no API key configured).

**What I can understand:**

File Operations:
- "read <filename>" - Read a file's contents
- "list files" or "show directory" - List files in current directory
- "show project structure" - Show the file tree

Commands:
- "run <command>" - Execute a shell command
- "git status" - Check git status
- "show current directory" - Show pwd

Tips:
- For full LLM capabilities, set ANTHROPIC_API_KEY
- Use /help for CLI commands
- Complex tasks will auto-enter PLAN mode

What would you like me to help with?"""

    def continue_with_tool_results(
        self,
        messages: list[Message],
        tool_rounds: list[dict],
        tools: list[dict] = None,
        system: str = None,
    ) -> LLMResponse:
        """Smart mock summarizes results and may suggest next steps."""
        # Summarize what happened
        summaries = []
        for rnd in tool_rounds:
            for result in rnd.get("results", []):
                if result.is_error:
                    summaries.append(f"Error: {result.content[:100]}")
                else:
                    summaries.append(f"Success: {result.content[:100]}...")

        return LLMResponse(
            content="Tool execution completed:\n" + "\n".join(summaries)
        )

    def is_available(self) -> bool:
        """Smart mock is always available."""
        return True

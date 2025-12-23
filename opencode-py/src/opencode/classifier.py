"""Input type classification."""

import re
from enum import Enum


class InputType(Enum):
    """Types of user input."""
    COMMAND = "command"      # /help, /plan, /build
    SHELL = "shell"          # ls -la, git status
    CHAT = "chat"            # natural language


class Classifier:
    """Classify user input into types."""

    # Known shell binaries
    SHELL_BINARIES = {
        # File system
        "ls", "cd", "pwd", "cat", "head", "tail", "less", "more",
        "cp", "mv", "rm", "mkdir", "rmdir", "touch", "chmod", "chown",
        "find", "locate", "tree", "file", "stat", "du", "df",

        # Text processing
        "grep", "rg", "ag", "awk", "sed", "cut", "sort", "uniq",
        "wc", "diff", "patch", "tr", "tee",

        # Archives
        "tar", "zip", "unzip", "gzip", "gunzip", "bzip2",

        # Network
        "curl", "wget", "ssh", "scp", "rsync", "ping", "netstat",

        # Version control
        "git", "svn", "hg",

        # Package managers
        "npm", "yarn", "pnpm", "pip", "pip3", "pipx", "poetry",
        "cargo", "go", "gem", "bundle",
        "apt", "apt-get", "brew", "yum", "dnf", "pacman",

        # Languages/runtimes
        "python", "python3", "node", "deno", "bun", "ruby", "perl",
        "java", "javac", "kotlin", "scala",
        "rustc", "gcc", "g++", "clang", "make", "cmake",

        # Containers
        "docker", "docker-compose", "podman", "kubectl", "helm",

        # Misc
        "echo", "printf", "date", "cal", "which", "whereis", "whoami",
        "env", "export", "source", "alias", "history", "clear", "reset",
        "man", "help", "info", "true", "false", "test", "xargs",
    }

    # Shell operators that indicate a shell command
    SHELL_OPERATORS = re.compile(r'[|><;&`$()]')

    # Patterns that strongly indicate shell commands
    SHELL_PATTERNS = [
        re.compile(r'^\s*\./'),           # ./script
        re.compile(r'^\s*~/'),            # ~/path
        re.compile(r'^\s*/'),             # /absolute/path
        re.compile(r'\s+--?\w'),          # flags like -f or --flag
        re.compile(r'^\s*\w+='),          # VAR=value
    ]

    # Words that indicate natural language (not shell commands)
    NATURAL_LANGUAGE_MARKERS = {
        # Articles
        "a", "an", "the",
        # Prepositions
        "for", "with", "to", "from", "in", "on", "at", "by", "about",
        # Pronouns
        "i", "me", "my", "we", "us", "our", "you", "your",
        # Common verbs that suggest requests
        "please", "can", "could", "would", "should", "want", "need",
        "help", "show", "explain", "tell", "give", "create", "build",
        # Question words
        "what", "how", "why", "where", "when", "which", "who",
    }

    def classify(self, input_text: str) -> InputType:
        """Classify user input.

        Args:
            input_text: The raw user input.

        Returns:
            InputType indicating the classification.
        """
        text = input_text.strip()

        if not text:
            return InputType.CHAT

        # Check for slash commands
        if text.startswith("/"):
            return InputType.COMMAND

        # Check for shell patterns
        if self._is_shell_command(text):
            return InputType.SHELL

        return InputType.CHAT

    def _is_shell_command(self, text: str) -> bool:
        """Determine if input looks like a shell command."""
        # Check for shell operators
        if self.SHELL_OPERATORS.search(text):
            return True

        # Check for shell patterns
        for pattern in self.SHELL_PATTERNS:
            if pattern.search(text):
                return True

        # Check if first word is a known binary
        words = text.split()
        if not words:
            return False

        first_word = words[0].lower()

        # Remove any path prefix
        if "/" in first_word:
            first_word = first_word.split("/")[-1]

        if first_word not in self.SHELL_BINARIES:
            return False

        # First word is a shell binary, but check for natural language markers
        # "make a calculator" vs "make build"
        lower_words = {w.lower() for w in words[1:]}
        if lower_words & self.NATURAL_LANGUAGE_MARKERS:
            return False

        return True

    def extract_command(self, input_text: str) -> tuple[str, str]:
        """Extract command name and arguments from slash command.

        Args:
            input_text: Input starting with /

        Returns:
            Tuple of (command_name, arguments)
        """
        text = input_text.strip()
        if not text.startswith("/"):
            return "", text

        # Remove leading slash
        text = text[1:]

        # Split into command and args
        parts = text.split(maxsplit=1)
        command = parts[0].lower() if parts else ""
        args = parts[1] if len(parts) > 1 else ""

        return command, args

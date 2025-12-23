"""User configuration management."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from opencode.workspace import Workspace

import sys

# Python 3.11+ has tomllib built-in, older versions need tomli
if sys.version_info >= (3, 11):
    import tomllib as tomli
else:
    try:
        import tomli
    except ImportError:
        tomli = None


def _default_safe_commands() -> list[str]:
    """Get default safe commands (cross-platform)."""
    # Unix commands
    commands = [
        "ls", "pwd", "cat", "head", "tail", "less", "more",
        "echo", "which", "whoami", "date", "wc", "file",
        "tree", "find", "grep", "rg", "fd", "ag",
        "git status", "git log", "git diff", "git branch", "git show",
        "python --version", "python3 --version",
        "node --version", "npm --version", "yarn --version",
        "cargo --version", "rustc --version",
        "go version", "java --version",
    ]

    # Windows-specific commands
    if os.name == 'nt':
        commands.extend([
            "dir", "cd", "type", "where", "hostname",
            "systeminfo", "ver", "set",
            "git.exe status", "git.exe log", "git.exe diff",
            "python.exe --version", "node.exe --version",
        ])

    return commands


@dataclass
class Config:
    """OpenCode-Py configuration."""

    # LLM settings
    llm_provider: str = "anthropic"  # "anthropic", "openai", or "custom"
    llm_model: str = "claude-sonnet-4-20250514"
    api_key: str = ""
    base_url: str = ""  # For custom OpenAI-compatible endpoints

    # Complexity settings
    complexity_threshold: float = 0.6
    auto_plan_enabled: bool = True

    # Execution settings
    auto_execute_safe: bool = True
    safe_commands: list[str] = field(default_factory=_default_safe_commands)

    # Tool settings
    tool_timeout: int = 30
    checkpoint_enabled: bool = True

    @classmethod
    def load(cls, workspace: "Optional[Workspace]" = None) -> "Config":
        """Load configuration from files and environment.

        Load order (later overrides earlier):
        1. Global config (~/.opencode/config.toml or %APPDATA%/opencode/config.toml)
        2. Local config (.opencode/config.toml in workspace)
        3. Environment variables

        Args:
            workspace: Optional workspace for local config lookup.
        """
        config = cls()

        # 1. Load global config (cross-platform)
        if os.name == 'nt':  # Windows
            appdata = os.environ.get('APPDATA')
            if appdata:
                global_config = Path(appdata) / "opencode" / "config.toml"
            else:
                global_config = Path.home() / ".opencode" / "config.toml"
        else:
            global_config = Path.home() / ".opencode" / "config.toml"

        if global_config.exists():
            config._load_from_file(global_config)

        # 2. Load local workspace config (only from initialized workspaces)
        if workspace and workspace.is_initialized and workspace.local_config_path:
            if workspace.local_config_path.exists():
                config._load_from_file(workspace.local_config_path)
        # No fallback - local config only loads from initialized workspaces

        # 3. Environment variable overrides
        config._load_from_env()

        return config

    def _load_from_file(self, path: Path) -> None:
        """Load configuration from a TOML file."""
        if tomli is None:
            return

        try:
            with open(path, "rb") as f:
                data = tomli.load(f)

            # LLM settings
            if "llm" in data:
                llm = data["llm"]
                if "provider" in llm:
                    self.llm_provider = llm["provider"]
                if "model" in llm:
                    self.llm_model = llm["model"]
                if "api_key" in llm:
                    self.api_key = llm["api_key"]
                if "base_url" in llm:
                    self.base_url = llm["base_url"]

            # Complexity settings
            if "complexity" in data:
                comp = data["complexity"]
                if "threshold" in comp:
                    self.complexity_threshold = float(comp["threshold"])
                if "auto_plan" in comp:
                    self.auto_plan_enabled = bool(comp["auto_plan"])

            # Execution settings
            if "execution" in data:
                exe = data["execution"]
                if "auto_execute_safe" in exe:
                    self.auto_execute_safe = bool(exe["auto_execute_safe"])
                if "safe_commands" in exe:
                    self.safe_commands = list(exe["safe_commands"])
                if "tool_timeout" in exe:
                    self.tool_timeout = int(exe["tool_timeout"])
                if "checkpoint_enabled" in exe:
                    self.checkpoint_enabled = bool(exe["checkpoint_enabled"])

        except Exception:
            pass  # Silently ignore config errors

    def _load_from_env(self) -> None:
        """Load configuration from environment variables."""
        # Explicit overrides first
        if provider := os.environ.get("OPENCODE_LLM_PROVIDER"):
            self.llm_provider = provider
        if model := os.environ.get("OPENCODE_LLM_MODEL"):
            self.llm_model = model
        if base_url := os.environ.get("OPENCODE_BASE_URL"):
            self.base_url = base_url
            if self.llm_provider == "anthropic":
                self.llm_provider = "custom"

        # Generic API key (highest priority)
        if key := os.environ.get("OPENCODE_API_KEY"):
            self.api_key = key
        # Provider-specific keys (respect config provider setting)
        elif self.llm_provider == "openai" and (key := os.environ.get("OPENAI_API_KEY")):
            self.api_key = key
        elif self.llm_provider == "anthropic" and (key := os.environ.get("ANTHROPIC_API_KEY")):
            self.api_key = key
        # Fallback: auto-detect provider from available keys
        elif not self.api_key:
            if key := os.environ.get("ANTHROPIC_API_KEY"):
                self.api_key = key
                if self.llm_provider == "anthropic":  # Only set if still default
                    pass  # Keep anthropic
            elif key := os.environ.get("OPENAI_API_KEY"):
                self.api_key = key
                self.llm_provider = "openai"

        if threshold := os.environ.get("OPENCODE_COMPLEXITY_THRESHOLD"):
            try:
                self.complexity_threshold = float(threshold)
            except ValueError:
                pass

    def save(self, path: Optional[Path] = None) -> None:
        """Save configuration to a TOML file."""
        if path is None:
            path = Path.home() / ".opencode" / "config.toml"

        path.parent.mkdir(parents=True, exist_ok=True)

        base_url_line = f'base_url = "{self.base_url}"' if self.base_url else '# base_url = "http://localhost:11434/v1"  # For custom providers'
        content = f'''# OpenCode-Py Configuration

[llm]
# Provider: "anthropic", "openai", or "custom"
provider = "{self.llm_provider}"
model = "{self.llm_model}"
# api_key = ""  # Better to use env vars: ANTHROPIC_API_KEY, OPENAI_API_KEY
{base_url_line}

# Examples:
# Anthropic:  provider = "anthropic", model = "claude-sonnet-4-20250514"
# OpenAI:     provider = "openai", model = "gpt-4o"
# Ollama:     provider = "custom", model = "llama3", base_url = "http://localhost:11434/v1"
# LM Studio:  provider = "custom", model = "local-model", base_url = "http://localhost:1234/v1"

[complexity]
threshold = {self.complexity_threshold}
auto_plan = {str(self.auto_plan_enabled).lower()}

[execution]
auto_execute_safe = {str(self.auto_execute_safe).lower()}
tool_timeout = {self.tool_timeout}
checkpoint_enabled = {str(self.checkpoint_enabled).lower()}

# safe_commands = ["ls", "pwd", "cat", ...]
'''
        path.write_text(content)

    def is_safe_command(self, command: str) -> bool:
        """Check if a command is in the safe whitelist (cross-platform)."""
        cmd_lower = command.lower().strip()

        # Exact match
        if cmd_lower in self.safe_commands:
            return True

        # Check if command starts with a safe prefix
        first_word = cmd_lower.split()[0] if cmd_lower else ""

        # Unix safe prefixes
        safe_prefixes = {
            "ls", "pwd", "cat", "head", "tail", "less", "more",
            "echo", "which", "whoami", "date", "wc", "file", "tree",
        }

        # Windows safe prefixes
        if os.name == 'nt':
            safe_prefixes.update({
                "dir", "type", "where", "hostname", "ver", "set",
            })

        if first_word in safe_prefixes:
            return True

        # Git read-only commands (works on both platforms)
        git_prefixes = ("git status", "git log", "git diff",
                        "git branch", "git show", "git remote -v",
                        "git.exe status", "git.exe log", "git.exe diff")
        if cmd_lower.startswith(git_prefixes):
            return True

        # Version checks
        if "--version" in cmd_lower or "version" == cmd_lower.split()[-1]:
            return True

        return False

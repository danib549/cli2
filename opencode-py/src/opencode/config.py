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
class ConfigSource:
    """Track where a config value came from."""
    global_config: Optional[Path] = None
    local_config: Optional[Path] = None
    loaded_from: str = "default"  # "default", "global", "local", "env"
    errors: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        parts = []
        if self.global_config:
            parts.append(f"Global: {self.global_config}")
        if self.local_config:
            parts.append(f"Local: {self.local_config}")
        parts.append(f"Active: {self.loaded_from}")
        if self.errors:
            parts.append(f"Errors: {', '.join(self.errors)}")
        return " | ".join(parts)


@dataclass
class Config:
    """OpenCode-Py configuration."""

    # LLM settings
    llm_provider: str = "anthropic"  # "anthropic", "openai", or "custom"
    llm_model: str = "claude-sonnet-4-20250514"
    api_key: str = ""
    base_url: str = ""  # For custom OpenAI-compatible endpoints
    stream: bool = True  # Enable streaming responses (set to False if streaming doesn't work)

    # SSL/TLS settings (for enterprise environments)
    ssl_cert_path: str = ""  # Path to CA bundle or certificate file
    ssl_verify: bool = True  # Set to False to disable SSL verification (not recommended)

    # Complexity settings
    complexity_threshold: float = 0.6
    auto_plan_enabled: bool = True

    # Execution settings
    auto_execute_safe: bool = True
    safe_commands: list[str] = field(default_factory=_default_safe_commands)

    # Tool settings
    tool_timeout: int = 30
    checkpoint_enabled: bool = True

    # Debug settings
    debug: bool = False

    # Config source tracking (not loaded from file)
    _source: ConfigSource = field(default_factory=ConfigSource)

    def get_ssl_context(self) -> Optional[str | bool]:
        """Get SSL verification setting for HTTP clients.

        Returns:
            - Path to cert file if ssl_cert_path is set
            - False if ssl_verify is False
            - True (default verification) otherwise
        """
        if self.ssl_cert_path:
            # Resolve path (support ~ and relative paths)
            cert_path = Path(self.ssl_cert_path).expanduser()
            if cert_path.exists():
                return str(cert_path)
            else:
                # Try relative to config directory
                if self._source.global_config:
                    alt_path = self._source.global_config.parent / self.ssl_cert_path
                    if alt_path.exists():
                        return str(alt_path)
                if self._source.local_config:
                    alt_path = self._source.local_config.parent / self.ssl_cert_path
                    if alt_path.exists():
                        return str(alt_path)
        if not self.ssl_verify:
            return False
        return True

    @classmethod
    def load(cls, workspace: "Optional[Workspace]" = None, debug: bool = False) -> "Config":
        """Load configuration from files and environment.

        Load order (later overrides earlier):
        1. Global config (~/.opencode/config.toml or %APPDATA%/opencode/config.toml)
        2. Local config (.opencode/config.toml in workspace)
        3. Environment variables

        Args:
            workspace: Optional workspace for local config lookup.
            debug: Print debug info about config loading.
        """
        config = cls()
        config._source = ConfigSource()

        # 1. Determine global config path (cross-platform)
        if os.name == 'nt':  # Windows
            appdata = os.environ.get('APPDATA')
            if appdata:
                global_config = Path(appdata) / "opencode" / "config.toml"
            else:
                global_config = Path.home() / ".opencode" / "config.toml"
        else:  # Linux/macOS
            global_config = Path.home() / ".opencode" / "config.toml"

        # 2. Load global config
        if global_config.exists():
            success, error = config._load_from_file(global_config)
            if success:
                config._source.global_config = global_config
                config._source.loaded_from = "global"
                if debug:
                    print(f"\033[90m[Config] Loaded global: {global_config}\033[0m")
            elif error:
                config._source.errors.append(f"global: {error}")
                if debug:
                    print(f"\033[33m[Config] Error loading global: {error}\033[0m")
        elif debug:
            print(f"\033[90m[Config] No global config at: {global_config}\033[0m")

        # 3. Load local workspace config (only from initialized workspaces)
        local_config = None
        if workspace and workspace.is_initialized and workspace.local_config_path:
            local_config = workspace.local_config_path

        if local_config and local_config.exists():
            success, error = config._load_from_file(local_config)
            if success:
                config._source.local_config = local_config
                config._source.loaded_from = "local"
                if debug:
                    print(f"\033[90m[Config] Loaded local: {local_config}\033[0m")
            elif error:
                config._source.errors.append(f"local: {error}")
                if debug:
                    print(f"\033[33m[Config] Error loading local: {error}\033[0m")
        elif debug and local_config:
            print(f"\033[90m[Config] No local config at: {local_config}\033[0m")

        # 4. Environment variable overrides
        env_overrides = config._load_from_env()
        if env_overrides:
            config._source.loaded_from = "env"
            if debug:
                print(f"\033[90m[Config] Env overrides: {', '.join(env_overrides)}\033[0m")

        # 5. Check debug flag from env
        if os.environ.get("OPENCODE_DEBUG", "").lower() in ("1", "true", "yes"):
            config.debug = True

        if debug:
            print(f"\033[90m[Config] Provider: {config.llm_provider}, Model: {config.llm_model}\033[0m")
            print(f"\033[90m[Config] API Key: {'set' if config.api_key else 'NOT SET'}\033[0m")

        return config

    @classmethod
    def get_global_config_path(cls) -> Path:
        """Get the global config path for the current platform."""
        if os.name == 'nt':  # Windows
            appdata = os.environ.get('APPDATA')
            if appdata:
                return Path(appdata) / "opencode" / "config.toml"
        return Path.home() / ".opencode" / "config.toml"

    def show_config_info(self) -> str:
        """Return a summary of current config and sources."""
        lines = [
            "Configuration:",
            f"  Provider: {self.llm_provider}",
            f"  Model: {self.llm_model}",
            f"  API Key: {'configured' if self.api_key else 'NOT SET'}",
            f"  Base URL: {self.base_url or '(default)'}",
            f"  Streaming: {self.stream}",
            f"  SSL Cert: {self.ssl_cert_path or '(system default)'}",
            f"  SSL Verify: {self.ssl_verify}",
            "",
            "Sources:",
        ]
        if self._source.global_config:
            lines.append(f"  Global: {self._source.global_config}")
        else:
            lines.append(f"  Global: (not found at {self.get_global_config_path()})")
        if self._source.local_config:
            lines.append(f"  Local: {self._source.local_config}")
        else:
            lines.append(f"  Local: (none)")
        lines.append(f"  Active source: {self._source.loaded_from}")
        if self._source.errors:
            lines.append(f"  Errors: {', '.join(self._source.errors)}")
        return "\n".join(lines)

    @classmethod
    def show_api_key_help(cls, provider: str = "anthropic") -> str:
        """Show platform-specific instructions for setting API key.

        Args:
            provider: The LLM provider ("anthropic" or "openai")

        Returns:
            Formatted help text with commands for all platforms.
        """
        if provider == "openai":
            env_var = "OPENAI_API_KEY"
            get_key_url = "https://platform.openai.com/api-keys"
        else:
            env_var = "ANTHROPIC_API_KEY"
            get_key_url = "https://console.anthropic.com/settings/keys"

        return f'''
Setting up {provider.upper()} API Key
{'=' * 40}

1. Get your API key from: {get_key_url}

2. Set it using ONE of these methods:

   WINDOWS (Command Prompt) - temporary:
   set {env_var}=sk-your-key-here

   WINDOWS (PowerShell) - temporary:
   $env:{env_var}="sk-your-key-here"

   WINDOWS (permanent via System Properties):
   setx {env_var} "sk-your-key-here"

   LINUX/MAC (temporary):
   export {env_var}=sk-your-key-here

   LINUX/MAC (permanent - add to ~/.bashrc or ~/.zshrc):
   echo 'export {env_var}=sk-your-key-here' >> ~/.bashrc
   source ~/.bashrc

   OR store in config file (less secure):
   Edit {cls.get_global_config_path()}
   Add: api_key = "sk-your-key-here" under [llm]

3. Verify it's set:
   WINDOWS: echo %{env_var}%
   LINUX/MAC: echo ${env_var}
'''

    @classmethod
    def quick_setup(cls, api_key: str = "", provider: str = "") -> "Config":
        """Quick one-line setup for common scenarios.

        Args:
            api_key: API key (if empty, will prompt or show help)
            provider: Provider name (auto-detect from key prefix if empty)

        Returns:
            Configured Config instance.

        Examples:
            # Just show help
            Config.quick_setup()

            # Setup with key
            Config.quick_setup("sk-ant-...")

            # Force provider
            Config.quick_setup("my-key", provider="openai")
        """
        # Auto-detect provider from key prefix
        if not provider and api_key:
            if api_key.startswith("sk-ant-"):
                provider = "anthropic"
            elif api_key.startswith("sk-"):
                provider = "openai"
            else:
                provider = "anthropic"  # Default

        if not provider:
            provider = "anthropic"

        # No key provided - show help
        if not api_key:
            print(cls.show_api_key_help(provider))
            print("\nQuick setup:")
            print(f'  Config.quick_setup("your-api-key-here")')
            print(f'  Config.quick_setup("your-key", provider="{provider}")')
            return cls.load()

        # Create/update global config with the key
        config = cls(
            llm_provider=provider,
            api_key=api_key,
            llm_model="claude-sonnet-4-20250514" if provider == "anthropic" else "gpt-4o",
        )
        config_path = cls.get_global_config_path()
        config.save(config_path)

        print(f"Config saved to: {config_path}")
        print(f"Provider: {provider}")
        print(f"API Key: {'*' * 20}...{api_key[-4:]}")

        # Warn about security
        print("\nNote: API key stored in config file.")
        print("For better security, use environment variables instead.")
        print(cls.show_api_key_help(provider))

        return config

    def _load_from_file(self, path: Path) -> tuple[bool, str]:
        """Load configuration from a TOML file.

        Returns:
            Tuple of (success: bool, error_message: str)
        """
        if tomli is None:
            return False, "tomli/tomllib not available - install tomli for Python <3.11"

        try:
            with open(path, "rb") as f:
                data = tomli.load(f)

            # LLM settings - only override if value is non-empty
            if "llm" in data:
                llm = data["llm"]
                if "provider" in llm and llm["provider"]:
                    self.llm_provider = llm["provider"]
                if "model" in llm and llm["model"]:
                    self.llm_model = llm["model"]
                if "api_key" in llm and llm["api_key"]:
                    self.api_key = llm["api_key"]
                if "base_url" in llm and llm["base_url"]:
                    self.base_url = llm["base_url"]
                if "stream" in llm:
                    self.stream = bool(llm["stream"])

            # SSL/TLS settings
            if "ssl" in data:
                ssl = data["ssl"]
                if "cert_path" in ssl and ssl["cert_path"]:
                    self.ssl_cert_path = ssl["cert_path"]
                if "verify" in ssl:
                    self.ssl_verify = bool(ssl["verify"])

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
                if "safe_commands" in exe and exe["safe_commands"]:
                    self.safe_commands = list(exe["safe_commands"])
                if "tool_timeout" in exe:
                    self.tool_timeout = int(exe["tool_timeout"])
                if "checkpoint_enabled" in exe:
                    self.checkpoint_enabled = bool(exe["checkpoint_enabled"])

            # Debug settings
            if "debug" in data:
                self.debug = bool(data["debug"])

            return True, ""

        except FileNotFoundError:
            return False, f"File not found: {path}"
        except Exception as e:
            return False, str(e)

    def _load_from_env(self) -> list[str]:
        """Load configuration from environment variables.

        Returns:
            List of environment variables that were applied.
        """
        overrides = []

        # Explicit overrides first
        if provider := os.environ.get("OPENCODE_LLM_PROVIDER"):
            self.llm_provider = provider
            overrides.append("OPENCODE_LLM_PROVIDER")
        if model := os.environ.get("OPENCODE_LLM_MODEL"):
            self.llm_model = model
            overrides.append("OPENCODE_LLM_MODEL")
        if base_url := os.environ.get("OPENCODE_BASE_URL"):
            self.base_url = base_url
            overrides.append("OPENCODE_BASE_URL")
            if self.llm_provider == "anthropic":
                self.llm_provider = "custom"
        if stream := os.environ.get("OPENCODE_STREAM"):
            self.stream = stream.lower() in ("1", "true", "yes", "on")
            overrides.append("OPENCODE_STREAM")

        # Generic API key (highest priority)
        if key := os.environ.get("OPENCODE_API_KEY"):
            self.api_key = key
            overrides.append("OPENCODE_API_KEY")
        # Provider-specific keys (respect config provider setting)
        elif self.llm_provider == "openai" and (key := os.environ.get("OPENAI_API_KEY")):
            self.api_key = key
            overrides.append("OPENAI_API_KEY")
        elif self.llm_provider == "anthropic" and (key := os.environ.get("ANTHROPIC_API_KEY")):
            self.api_key = key
            overrides.append("ANTHROPIC_API_KEY")
        # Fallback: auto-detect provider from available keys
        elif not self.api_key:
            if key := os.environ.get("ANTHROPIC_API_KEY"):
                self.api_key = key
                overrides.append("ANTHROPIC_API_KEY")
            elif key := os.environ.get("OPENAI_API_KEY"):
                self.api_key = key
                self.llm_provider = "openai"
                overrides.append("OPENAI_API_KEY")

        if threshold := os.environ.get("OPENCODE_COMPLEXITY_THRESHOLD"):
            try:
                self.complexity_threshold = float(threshold)
                overrides.append("OPENCODE_COMPLEXITY_THRESHOLD")
            except ValueError:
                pass

        # SSL settings from environment
        if ssl_cert := os.environ.get("OPENCODE_SSL_CERT_PATH"):
            self.ssl_cert_path = ssl_cert
            overrides.append("OPENCODE_SSL_CERT_PATH")
        elif ssl_cert := os.environ.get("SSL_CERT_FILE"):
            # Standard env var used by many tools
            self.ssl_cert_path = ssl_cert
            overrides.append("SSL_CERT_FILE")
        elif ssl_cert := os.environ.get("REQUESTS_CA_BUNDLE"):
            # Used by Python requests library
            self.ssl_cert_path = ssl_cert
            overrides.append("REQUESTS_CA_BUNDLE")

        if ssl_verify := os.environ.get("OPENCODE_SSL_VERIFY"):
            self.ssl_verify = ssl_verify.lower() not in ("0", "false", "no", "off")
            overrides.append("OPENCODE_SSL_VERIFY")

        return overrides

    @classmethod
    def init_global(
        cls,
        provider: str = "anthropic",
        model: str = "",
        api_key: str = "",
        base_url: str = "",
        force: bool = False,
    ) -> tuple[Path, bool]:
        """Initialize global config file with sensible defaults.

        Automatically detects Windows vs Linux and uses correct path.

        Args:
            provider: LLM provider ("anthropic", "openai", "custom")
            model: Model name (default: provider-appropriate default)
            api_key: API key (recommend using env var instead)
            base_url: Custom endpoint URL (for "custom" provider)
            force: Overwrite existing config

        Returns:
            Tuple of (config_path, created: bool)
        """
        config_path = cls.get_global_config_path()

        # Don't overwrite unless forced
        if config_path.exists() and not force:
            return config_path, False

        # Set provider-appropriate defaults
        if not model:
            if provider == "anthropic":
                model = "claude-sonnet-4-20250514"
            elif provider == "openai":
                model = "gpt-4o"
            else:
                model = "llama3"

        # Create config
        config = cls(
            llm_provider=provider,
            llm_model=model,
            api_key=api_key,
            base_url=base_url,
        )
        config.save(config_path)

        return config_path, True

    @classmethod
    def setup_wizard(cls) -> "Config":
        """Interactive setup wizard for configuration.

        Returns:
            Configured Config instance.
        """
        import sys

        print("OpenCode-Py Configuration Setup")
        print("=" * 40)
        print()

        # Detect platform
        if os.name == 'nt':
            platform_name = "Windows"
        elif sys.platform == 'darwin':
            platform_name = "macOS"
        else:
            platform_name = "Linux"

        config_path = cls.get_global_config_path()
        print(f"Platform: {platform_name}")
        print(f"Config path: {config_path}")
        print()

        # Check existing config
        if config_path.exists():
            print(f"Existing config found at {config_path}")
            response = input("Overwrite? [y/N]: ").strip().lower()
            if response != 'y':
                print("Setup cancelled.")
                return cls.load()

        # Provider selection
        print("Available providers:")
        print("  1. anthropic (Claude)")
        print("  2. openai (GPT-4)")
        print("  3. custom (Ollama, LM Studio, etc.)")
        print()

        choice = input("Select provider [1]: ").strip() or "1"
        if choice == "2":
            provider = "openai"
            default_model = "gpt-4o"
        elif choice == "3":
            provider = "custom"
            default_model = "llama3"
        else:
            provider = "anthropic"
            default_model = "claude-sonnet-4-20250514"

        # Model
        model = input(f"Model [{default_model}]: ").strip() or default_model

        # Base URL for custom
        base_url = ""
        if provider == "custom":
            base_url = input("Base URL [http://localhost:11434/v1]: ").strip()
            base_url = base_url or "http://localhost:11434/v1"

        # API key
        print()
        print("API Key options:")
        print("  1. Set via environment variable (recommended)")
        print("  2. Store in config file")
        print()

        key_choice = input("Select [1]: ").strip() or "1"
        api_key = ""
        if key_choice == "2":
            api_key = input("Enter API key: ").strip()
            print("\nNote: Storing API keys in files is less secure than env vars.")

        # Create config
        config_path, created = cls.init_global(
            provider=provider,
            model=model,
            api_key=api_key,
            base_url=base_url,
            force=True,
        )

        print()
        print(f"Config saved to: {config_path}")

        if not api_key:
            env_var = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
            print()
            print(f"Set your API key:")
            if os.name == 'nt':
                print(f"  Windows:  set {env_var}=your-key-here")
                print(f"  PowerShell: $env:{env_var}=\"your-key-here\"")
            else:
                print(f"  export {env_var}=your-key-here")
                print(f"  Add to ~/.bashrc or ~/.zshrc to persist")

        return cls.load()

    def save(self, path: Optional[Path] = None) -> None:
        """Save configuration to a TOML file."""
        if path is None:
            path = self.get_global_config_path()

        path.parent.mkdir(parents=True, exist_ok=True)

        base_url_line = f'base_url = "{self.base_url}"' if self.base_url else '# base_url = ""'
        stream_line = f'stream = {str(self.stream).lower()}'

        # SSL section
        if self.ssl_cert_path or not self.ssl_verify:
            ssl_section = f'''
[ssl]
# SSL/TLS settings for enterprise environments with custom certificates
cert_path = "{self.ssl_cert_path}"
verify = {str(self.ssl_verify).lower()}
'''
        else:
            ssl_section = '''
# [ssl]
# cert_path = "/path/to/ca-bundle.crt"
# verify = true
'''

        content = f'''# OpenCode-Py Configuration
# ========================
#
# This file configures the OpenCode-Py CLI agent.
# Settings here can be overridden by environment variables.
#
# Config priority (highest to lowest):
#   1. Environment variables
#   2. Local config  (.opencode/config.toml in project)
#   3. Global config (this file)

# =============================================================================
# LLM PROVIDER SETTINGS
# =============================================================================

[llm]
# Provider options: "anthropic", "openai", or "custom"
provider = "{self.llm_provider}"

# Model name (provider-specific)
model = "{self.llm_model}"

# API Key - RECOMMENDED: Use environment variables instead of storing here
# Environment variables: ANTHROPIC_API_KEY, OPENAI_API_KEY, or OPENCODE_API_KEY
# api_key = "sk-..."

# Base URL - Override the default API endpoint
# Leave commented to use the provider's default endpoint
{base_url_line}

# Streaming - Set to false if you experience issues with streaming responses
{stream_line}

# -----------------------------------------------------------------------------
# PROVIDER EXAMPLES
# -----------------------------------------------------------------------------
#
# Anthropic (default):
#   provider = "anthropic"
#   model = "claude-sonnet-4-20250514"
#   # Uses ANTHROPIC_API_KEY env var
#
# OpenAI:
#   provider = "openai"
#   model = "gpt-4o"
#   # Uses OPENAI_API_KEY env var
#
# Azure OpenAI:
#   provider = "openai"
#   model = "gpt-4"
#   base_url = "https://YOUR-RESOURCE.openai.azure.com/openai/deployments/YOUR-DEPLOYMENT"
#   # Uses OPENAI_API_KEY env var with your Azure API key
#
# Ollama (local):
#   provider = "custom"
#   model = "llama3"
#   base_url = "http://localhost:11434/v1"
#
# LM Studio (local):
#   provider = "custom"
#   model = "local-model"
#   base_url = "http://localhost:1234/v1"
#
# OpenAI-compatible API:
#   provider = "custom"
#   model = "your-model"
#   base_url = "https://your-api-endpoint.com/v1"

# =============================================================================
# SSL/TLS SETTINGS
# =============================================================================
#
# For corporate environments with custom CA certificates or proxies.
# Environment variables (auto-detected):
#   OPENCODE_SSL_CERT_PATH, SSL_CERT_FILE, REQUESTS_CA_BUNDLE
#   OPENCODE_SSL_VERIFY=false (to disable verification)
{ssl_section}
# Examples:
#
# Corporate proxy with custom CA:
#   [ssl]
#   cert_path = "/etc/pki/tls/certs/corporate-ca-bundle.crt"
#
# Windows with custom cert:
#   [ssl]
#   cert_path = "C:\\certs\\corporate-ca.crt"
#
# Disable verification (NOT recommended, testing only):
#   [ssl]
#   verify = false

# =============================================================================
# COMPLEXITY & AUTO-PLANNING
# =============================================================================

[complexity]
# Threshold for auto-triggering plan mode (0.0 to 1.0)
# Higher = fewer tasks trigger planning, Lower = more tasks trigger planning
threshold = {self.complexity_threshold}

# Enable automatic plan mode for complex tasks
auto_plan = {str(self.auto_plan_enabled).lower()}

# =============================================================================
# EXECUTION SETTINGS
# =============================================================================

[execution]
# Auto-execute safe commands without confirmation (ls, pwd, git status, etc.)
auto_execute_safe = {str(self.auto_execute_safe).lower()}

# Tool execution timeout in seconds
tool_timeout = {self.tool_timeout}

# Create git checkpoints before destructive operations
checkpoint_enabled = {str(self.checkpoint_enabled).lower()}

# Custom safe commands (in addition to defaults)
# safe_commands = ["npm test", "cargo build", "make"]

# =============================================================================
# ENVIRONMENT VARIABLES REFERENCE
# =============================================================================
#
# API Keys:
#   ANTHROPIC_API_KEY      - Anthropic/Claude API key
#   OPENAI_API_KEY         - OpenAI API key
#   OPENCODE_API_KEY       - Generic API key (overrides provider-specific)
#
# Provider settings:
#   OPENCODE_LLM_PROVIDER  - Override provider (anthropic/openai/custom)
#   OPENCODE_LLM_MODEL     - Override model name
#   OPENCODE_BASE_URL      - Override base URL
#   OPENCODE_STREAM        - Enable/disable streaming (true/false)
#
# SSL settings:
#   OPENCODE_SSL_CERT_PATH - Path to CA certificate bundle
#   OPENCODE_SSL_VERIFY    - Enable/disable SSL verification (true/false)
#   SSL_CERT_FILE          - Standard cert path (auto-detected)
#   REQUESTS_CA_BUNDLE     - Python requests cert path (auto-detected)
#
# Debug:
#   OPENCODE_DEBUG=1       - Enable debug output
#
# -----------------------------------------------------------------------------
# SETTING ENVIRONMENT VARIABLES
# -----------------------------------------------------------------------------
#
# Linux/macOS (temporary):
#   export ANTHROPIC_API_KEY="sk-ant-..."
#   export OPENCODE_BASE_URL="https://api.example.com/v1"
#
# Linux/macOS (permanent - add to ~/.bashrc or ~/.zshrc):
#   echo 'export ANTHROPIC_API_KEY="sk-ant-..."' >> ~/.bashrc
#
# Windows Command Prompt (temporary):
#   set ANTHROPIC_API_KEY=sk-ant-...
#   set OPENCODE_BASE_URL=https://api.example.com/v1
#
# Windows PowerShell (temporary):
#   $env:ANTHROPIC_API_KEY="sk-ant-..."
#   $env:OPENCODE_BASE_URL="https://api.example.com/v1"
#
# Windows (permanent via System Properties):
#   setx ANTHROPIC_API_KEY "sk-ant-..."
#   # Then restart your terminal
#
# Windows (permanent via PowerShell profile):
#   Add to $PROFILE:
#   $env:ANTHROPIC_API_KEY="sk-ant-..."
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

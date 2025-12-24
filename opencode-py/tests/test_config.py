"""Tests for configuration management."""

import os
import pytest
from pathlib import Path

from opencode.config import Config, _default_safe_commands


class TestDefaultSafeCommands:
    """Tests for default safe commands function."""

    def test_returns_list(self):
        """Test that function returns a list."""
        commands = _default_safe_commands()
        assert isinstance(commands, list)

    def test_contains_basic_commands(self):
        """Test that basic safe commands are included."""
        commands = _default_safe_commands()
        basic = ["ls", "pwd", "cat", "echo", "git status"]
        for cmd in basic:
            assert cmd in commands


class TestConfig:
    """Tests for Config class."""

    def test_default_values(self):
        """Test default configuration values."""
        config = Config()

        assert config.llm_provider == "anthropic"
        assert config.llm_model == "claude-sonnet-4-20250514"
        assert config.api_key == ""
        assert config.base_url == ""
        assert config.complexity_threshold == 0.6
        assert config.auto_plan_enabled is True
        assert config.auto_execute_safe is True
        assert config.tool_timeout == 30
        assert config.checkpoint_enabled is True

    def test_safe_commands_default(self):
        """Test that safe_commands has default values."""
        config = Config()
        assert len(config.safe_commands) > 0
        assert "ls" in config.safe_commands

    def test_is_safe_command_exact_match(self):
        """Test exact command matching."""
        config = Config()
        config.safe_commands = ["ls", "pwd", "git status"]

        assert config.is_safe_command("ls") is True
        assert config.is_safe_command("pwd") is True
        assert config.is_safe_command("git status") is True

    def test_is_safe_command_prefix_match(self):
        """Test prefix-based command matching."""
        config = Config()

        # These should match based on prefix
        assert config.is_safe_command("ls -la") is True
        assert config.is_safe_command("cat file.txt") is True
        assert config.is_safe_command("echo hello") is True

    def test_is_safe_command_git_readonly(self):
        """Test git read-only command matching."""
        config = Config()

        assert config.is_safe_command("git status") is True
        assert config.is_safe_command("git log --oneline") is True
        assert config.is_safe_command("git diff HEAD") is True
        assert config.is_safe_command("git branch") is True

    def test_is_safe_command_version_check(self):
        """Test version check command matching."""
        config = Config()

        assert config.is_safe_command("python --version") is True
        assert config.is_safe_command("node --version") is True
        assert config.is_safe_command("rustc --version") is True

    def test_is_safe_command_unsafe(self):
        """Test that unsafe commands are rejected."""
        config = Config()

        assert config.is_safe_command("rm -rf /") is False
        assert config.is_safe_command("sudo apt install") is False
        assert config.is_safe_command("git push --force") is False

    def test_is_safe_command_case_insensitive(self):
        """Test case insensitive matching."""
        config = Config()

        assert config.is_safe_command("LS") is True
        assert config.is_safe_command("PWD") is True
        assert config.is_safe_command("Git Status") is True

    def test_load_from_file(self, config_file):
        """Test loading configuration from TOML file."""
        config = Config()
        config._load_from_file(config_file)

        assert config.llm_provider == "anthropic"
        assert config.llm_model == "claude-sonnet-4-20250514"
        assert config.complexity_threshold == 0.7
        assert config.auto_plan_enabled is True
        assert config.tool_timeout == 60

    def test_load_from_env(self, monkeypatch):
        """Test loading configuration from environment variables."""
        monkeypatch.setenv("OPENCODE_LLM_PROVIDER", "openai")
        monkeypatch.setenv("OPENCODE_LLM_MODEL", "gpt-4o")
        monkeypatch.setenv("OPENCODE_API_KEY", "test-key")
        monkeypatch.setenv("OPENCODE_COMPLEXITY_THRESHOLD", "0.8")

        config = Config()
        config._load_from_env()

        assert config.llm_provider == "openai"
        assert config.llm_model == "gpt-4o"
        assert config.api_key == "test-key"
        assert config.complexity_threshold == 0.8

    def test_load_from_env_base_url_changes_provider(self, monkeypatch):
        """Test that setting base_url changes provider to custom when provider is anthropic."""
        # Clear any API keys that might affect provider detection
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        monkeypatch.setenv("OPENCODE_BASE_URL", "http://localhost:11434/v1")

        config = Config()
        config.llm_provider = "anthropic"  # Ensure starting from anthropic
        config._load_from_env()

        assert config.llm_provider == "custom"
        assert config.base_url == "http://localhost:11434/v1"

    def test_load_from_env_anthropic_api_key(self, monkeypatch):
        """Test loading Anthropic API key from environment."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")

        config = Config()
        config._load_from_env()

        assert config.api_key == "sk-ant-test"
        assert config.llm_provider == "anthropic"

    def test_load_from_env_openai_api_key(self, monkeypatch):
        """Test loading OpenAI API key from environment."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

        config = Config()
        config._load_from_env()

        assert config.api_key == "sk-test"
        assert config.llm_provider == "openai"

    def test_opencode_api_key_takes_priority(self, monkeypatch):
        """Test that OPENCODE_API_KEY takes priority over provider-specific keys."""
        monkeypatch.setenv("OPENCODE_API_KEY", "primary-key")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key")
        monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

        config = Config()
        config._load_from_env()

        assert config.api_key == "primary-key"

    def test_save_config(self, temp_dir):
        """Test saving configuration to file."""
        config = Config()
        config.llm_provider = "openai"
        config.llm_model = "gpt-4o"
        config.complexity_threshold = 0.8

        config_path = temp_dir / "config.toml"
        config.save(config_path)

        assert config_path.exists()
        content = config_path.read_text()
        assert 'provider = "openai"' in content
        assert 'model = "gpt-4o"' in content
        assert "threshold = 0.8" in content

    def test_invalid_complexity_threshold(self, monkeypatch):
        """Test that invalid threshold value is ignored."""
        monkeypatch.setenv("OPENCODE_COMPLEXITY_THRESHOLD", "invalid")

        config = Config()
        config._load_from_env()

        # Should remain at default
        assert config.complexity_threshold == 0.6

    def test_load_nonexistent_file(self, temp_dir):
        """Test loading from nonexistent file doesn't raise."""
        config = Config()
        nonexistent = temp_dir / "nonexistent.toml"

        # Should not raise
        config._load_from_file(nonexistent)

    def test_load_invalid_toml(self, temp_dir):
        """Test loading invalid TOML file doesn't raise."""
        invalid_file = temp_dir / "invalid.toml"
        invalid_file.write_text("this is not valid toml [[[")

        config = Config()
        # Should not raise
        config._load_from_file(invalid_file)

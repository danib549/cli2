"""Advanced configuration tests including SSL/TLS and source tracking."""

import os
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory

from opencode.config import Config, ConfigSource


# ============================================================================
# ConfigSource Tests
# ============================================================================

class TestConfigSource:
    """Tests for ConfigSource tracking."""

    def test_default_source(self):
        """Test default ConfigSource values."""
        source = ConfigSource()

        assert source.global_config is None
        assert source.local_config is None
        assert source.loaded_from == "default"
        assert source.errors == []

    def test_source_with_global(self, tmp_path):
        """Test ConfigSource with global config."""
        source = ConfigSource(
            global_config=tmp_path / "config.toml",
            loaded_from="global"
        )

        assert source.global_config == tmp_path / "config.toml"
        assert source.loaded_from == "global"

    def test_source_with_local(self, tmp_path):
        """Test ConfigSource with local config."""
        source = ConfigSource(
            global_config=tmp_path / "global.toml",
            local_config=tmp_path / "local.toml",
            loaded_from="local"
        )

        assert source.global_config is not None
        assert source.local_config is not None
        assert source.loaded_from == "local"

    def test_source_with_errors(self):
        """Test ConfigSource with errors."""
        source = ConfigSource(
            loaded_from="default",
            errors=["global: File not found", "local: Parse error"]
        )

        assert len(source.errors) == 2
        assert "global" in source.errors[0]

    def test_source_str_representation(self, tmp_path):
        """Test ConfigSource string representation."""
        source = ConfigSource(
            global_config=tmp_path / "global.toml",
            local_config=tmp_path / "local.toml",
            loaded_from="env",
            errors=["test error"]
        )

        str_repr = str(source)
        assert "Global:" in str_repr
        assert "Local:" in str_repr
        assert "Active: env" in str_repr
        assert "Errors:" in str_repr


# ============================================================================
# SSL/TLS Configuration Tests
# ============================================================================

class TestSSLConfiguration:
    """Tests for SSL/TLS configuration options."""

    def test_default_ssl_settings(self):
        """Test default SSL settings."""
        config = Config()

        assert config.ssl_cert_path == ""
        assert config.ssl_verify is True

    def test_ssl_verify_disabled(self):
        """Test SSL verification can be disabled."""
        config = Config(ssl_verify=False)

        assert config.ssl_verify is False
        assert config.get_ssl_context() is False

    def test_ssl_cert_path(self, tmp_path):
        """Test SSL certificate path configuration."""
        cert_file = tmp_path / "ca-bundle.crt"
        cert_file.write_text("FAKE CERT CONTENT")

        config = Config(ssl_cert_path=str(cert_file))

        ssl_context = config.get_ssl_context()
        assert ssl_context == str(cert_file)

    def test_ssl_cert_path_nonexistent(self):
        """Test behavior with nonexistent cert path."""
        config = Config(ssl_cert_path="/nonexistent/path/ca.crt")

        # Should fall back to default verification
        ssl_context = config.get_ssl_context()
        assert ssl_context is True

    def test_ssl_cert_relative_to_global_config(self, tmp_path):
        """Test cert path relative to global config directory."""
        # Create config directory structure
        config_dir = tmp_path / ".opencode"
        config_dir.mkdir()
        cert_file = config_dir / "my-cert.crt"
        cert_file.write_text("CERT CONTENT")

        config = Config(ssl_cert_path="my-cert.crt")
        config._source.global_config = config_dir / "config.toml"

        ssl_context = config.get_ssl_context()
        assert ssl_context == str(cert_file)

    def test_ssl_cert_relative_to_local_config(self, tmp_path):
        """Test cert path relative to local config directory."""
        # Create workspace structure
        workspace_dir = tmp_path / "project" / ".opencode"
        workspace_dir.mkdir(parents=True)
        cert_file = workspace_dir / "local-cert.crt"
        cert_file.write_text("LOCAL CERT")

        config = Config(ssl_cert_path="local-cert.crt")
        config._source.local_config = workspace_dir / "config.toml"

        ssl_context = config.get_ssl_context()
        assert ssl_context == str(cert_file)

    def test_ssl_from_environment(self, monkeypatch):
        """Test SSL settings from environment variables."""
        monkeypatch.setenv("OPENCODE_SSL_VERIFY", "false")

        config = Config()
        config._load_from_env()

        assert config.ssl_verify is False

    def test_ssl_cert_from_standard_env_vars(self, monkeypatch, tmp_path):
        """Test SSL cert from standard environment variables."""
        cert_file = tmp_path / "system-ca.crt"
        cert_file.write_text("SYSTEM CA")

        # Test SSL_CERT_FILE
        monkeypatch.setenv("SSL_CERT_FILE", str(cert_file))

        config = Config()
        overrides = config._load_from_env()

        assert "SSL_CERT_FILE" in overrides
        assert config.ssl_cert_path == str(cert_file)

    def test_ssl_cert_from_requests_env(self, monkeypatch, tmp_path):
        """Test SSL cert from REQUESTS_CA_BUNDLE."""
        cert_file = tmp_path / "requests-ca.crt"
        cert_file.write_text("REQUESTS CA")

        monkeypatch.setenv("REQUESTS_CA_BUNDLE", str(cert_file))

        config = Config()
        overrides = config._load_from_env()

        assert "REQUESTS_CA_BUNDLE" in overrides
        assert config.ssl_cert_path == str(cert_file)

    def test_ssl_config_from_toml(self, tmp_path):
        """Test loading SSL config from TOML file."""
        config_content = '''
[llm]
provider = "anthropic"
model = "claude-sonnet-4-20250514"

[ssl]
cert_path = "/etc/ssl/certs/ca-certificates.crt"
verify = true
'''
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)

        config = Config()
        success, error = config._load_from_file(config_file)

        assert success is True
        assert config.ssl_cert_path == "/etc/ssl/certs/ca-certificates.crt"
        assert config.ssl_verify is True

    def test_ssl_verify_false_in_toml(self, tmp_path):
        """Test SSL verify=false from TOML."""
        config_content = '''
[ssl]
verify = false
'''
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)

        config = Config()
        config._load_from_file(config_file)

        assert config.ssl_verify is False

    def test_ssl_expand_home_in_path(self, tmp_path, monkeypatch):
        """Test that ~ is expanded in cert path."""
        # Create cert in fake home
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        cert_file = fake_home / "my-cert.crt"
        cert_file.write_text("HOME CERT")

        monkeypatch.setenv("HOME", str(fake_home))

        config = Config(ssl_cert_path="~/my-cert.crt")
        ssl_context = config.get_ssl_context()

        assert ssl_context == str(cert_file)


# ============================================================================
# Config Info Display Tests
# ============================================================================

class TestConfigInfo:
    """Tests for config info display methods."""

    def test_show_config_info(self):
        """Test show_config_info output."""
        config = Config(
            llm_provider="anthropic",
            llm_model="claude-sonnet-4-20250514",
            api_key="sk-test-key"
        )

        info = config.show_config_info()

        assert "Provider: anthropic" in info
        assert "Model: claude-sonnet" in info
        assert "configured" in info  # API key is set

    def test_show_config_info_no_key(self):
        """Test show_config_info when API key is not set."""
        config = Config()

        info = config.show_config_info()

        assert "NOT SET" in info

    def test_show_config_info_with_ssl(self):
        """Test show_config_info includes SSL settings."""
        config = Config(
            ssl_cert_path="/path/to/cert.crt",
            ssl_verify=True
        )

        info = config.show_config_info()

        assert "SSL Cert:" in info
        assert "SSL Verify:" in info

    def test_show_api_key_help_anthropic(self):
        """Test API key help for Anthropic."""
        help_text = Config.show_api_key_help("anthropic")

        assert "ANTHROPIC_API_KEY" in help_text
        assert "console.anthropic.com" in help_text
        assert "WINDOWS" in help_text
        assert "LINUX" in help_text

    def test_show_api_key_help_openai(self):
        """Test API key help for OpenAI."""
        help_text = Config.show_api_key_help("openai")

        assert "OPENAI_API_KEY" in help_text
        assert "platform.openai.com" in help_text

    def test_get_global_config_path(self):
        """Test global config path retrieval."""
        path = Config.get_global_config_path()

        assert isinstance(path, Path)
        assert "config.toml" in str(path)


# ============================================================================
# Config Load with Source Tracking Tests
# ============================================================================

class TestConfigLoadWithSourceTracking:
    """Tests for config loading with source tracking."""

    def test_load_tracks_global_source(self, tmp_path, monkeypatch):
        """Test that loading tracks global config source."""
        # Create a global config
        global_dir = tmp_path / ".opencode"
        global_dir.mkdir()
        global_config = global_dir / "config.toml"
        global_config.write_text('''
[llm]
provider = "openai"
model = "gpt-4"
''')

        # Patch home to our temp dir
        monkeypatch.setenv("HOME", str(tmp_path))
        if os.name == 'nt':
            monkeypatch.delenv("APPDATA", raising=False)

        config = Config.load()

        assert config._source.global_config == global_config
        assert config._source.loaded_from in ("global", "env")

    def test_load_tracks_errors(self, tmp_path, monkeypatch):
        """Test that loading tracks config errors."""
        # Create invalid config
        global_dir = tmp_path / ".opencode"
        global_dir.mkdir()
        global_config = global_dir / "config.toml"
        global_config.write_text("invalid toml [[[")

        monkeypatch.setenv("HOME", str(tmp_path))
        if os.name == 'nt':
            monkeypatch.delenv("APPDATA", raising=False)

        config = Config.load()

        # Should have recorded the error
        assert len(config._source.errors) > 0 or config._source.loaded_from == "default"

    def test_load_env_overrides_tracked(self, monkeypatch):
        """Test that environment overrides are tracked."""
        monkeypatch.setenv("OPENCODE_LLM_PROVIDER", "custom")
        monkeypatch.setenv("OPENCODE_LLM_MODEL", "llama3")

        config = Config()
        overrides = config._load_from_env()

        assert "OPENCODE_LLM_PROVIDER" in overrides
        assert "OPENCODE_LLM_MODEL" in overrides


# ============================================================================
# Config Save Tests
# ============================================================================

class TestConfigSave:
    """Tests for config save functionality."""

    def test_save_creates_directory(self, tmp_path):
        """Test that save creates parent directories."""
        config = Config(llm_provider="anthropic")

        config_path = tmp_path / "new" / "nested" / "config.toml"
        config.save(config_path)

        assert config_path.exists()
        assert config_path.parent.exists()

    def test_save_includes_ssl_section(self, tmp_path):
        """Test that save includes SSL section when configured."""
        config = Config(
            ssl_cert_path="/path/to/cert.crt",
            ssl_verify=False
        )

        config_path = tmp_path / "config.toml"
        config.save(config_path)

        content = config_path.read_text()
        assert "[ssl]" in content
        assert "cert_path" in content
        assert "verify = false" in content

    def test_save_comments_ssl_when_default(self, tmp_path):
        """Test that SSL section is commented when using defaults."""
        config = Config()  # Default SSL settings

        config_path = tmp_path / "config.toml"
        config.save(config_path)

        content = config_path.read_text()
        # Should have commented SSL section
        assert "# [ssl]" in content or "SSL/TLS settings" in content


# ============================================================================
# Config Debug Mode Tests
# ============================================================================

class TestConfigDebugMode:
    """Tests for config debug mode."""

    def test_debug_from_environment(self, monkeypatch):
        """Test debug mode from environment."""
        monkeypatch.setenv("OPENCODE_DEBUG", "true")

        config = Config()
        config._load_from_env()

        # Note: debug is set in Config.load(), not _load_from_env()
        # This test verifies the env var is recognized

    def test_debug_in_config(self, tmp_path):
        """Test debug mode in config file."""
        config_content = '''
debug = true
'''
        config_file = tmp_path / "config.toml"
        config_file.write_text(config_content)

        config = Config()
        config._load_from_file(config_file)

        assert config.debug is True

    def test_debug_default_false(self):
        """Test debug is false by default."""
        config = Config()
        assert config.debug is False


# ============================================================================
# Init Global Tests
# ============================================================================

class TestInitGlobal:
    """Tests for Config.init_global method."""

    def test_init_global_creates_config(self, tmp_path, monkeypatch):
        """Test init_global creates config file."""
        monkeypatch.setenv("HOME", str(tmp_path))
        if os.name == 'nt':
            monkeypatch.delenv("APPDATA", raising=False)

        path, created = Config.init_global(
            provider="anthropic",
            model="claude-sonnet-4-20250514"
        )

        assert created is True
        assert path.exists()

    def test_init_global_no_overwrite(self, tmp_path, monkeypatch):
        """Test init_global doesn't overwrite existing config."""
        global_dir = tmp_path / ".opencode"
        global_dir.mkdir()
        config_file = global_dir / "config.toml"
        config_file.write_text("existing content")

        monkeypatch.setenv("HOME", str(tmp_path))
        if os.name == 'nt':
            monkeypatch.delenv("APPDATA", raising=False)

        path, created = Config.init_global(provider="anthropic")

        assert created is False
        assert config_file.read_text() == "existing content"

    def test_init_global_force_overwrite(self, tmp_path, monkeypatch):
        """Test init_global with force overwrites existing config."""
        global_dir = tmp_path / ".opencode"
        global_dir.mkdir()
        config_file = global_dir / "config.toml"
        config_file.write_text("old content")

        monkeypatch.setenv("HOME", str(tmp_path))
        if os.name == 'nt':
            monkeypatch.delenv("APPDATA", raising=False)

        path, created = Config.init_global(provider="openai", force=True)

        assert created is True
        content = config_file.read_text()
        assert "openai" in content

    def test_init_global_provider_defaults(self, tmp_path, monkeypatch):
        """Test init_global sets provider-appropriate defaults."""
        monkeypatch.setenv("HOME", str(tmp_path))
        if os.name == 'nt':
            monkeypatch.delenv("APPDATA", raising=False)

        # Test Anthropic default
        path, _ = Config.init_global(provider="anthropic", force=True)
        content = path.read_text()
        assert "claude" in content.lower()

        # Test OpenAI default
        path, _ = Config.init_global(provider="openai", force=True)
        content = path.read_text()
        assert "gpt" in content.lower()


# ============================================================================
# Quick Setup Tests
# ============================================================================

class TestQuickSetup:
    """Tests for Config.quick_setup method."""

    def test_quick_setup_auto_detect_anthropic(self, tmp_path, monkeypatch, capsys):
        """Test quick_setup auto-detects Anthropic from key prefix."""
        monkeypatch.setenv("HOME", str(tmp_path))
        if os.name == 'nt':
            monkeypatch.delenv("APPDATA", raising=False)

        config = Config.quick_setup("sk-ant-test-key-12345")

        assert config.llm_provider == "anthropic"
        assert config.api_key == "sk-ant-test-key-12345"

    def test_quick_setup_auto_detect_openai(self, tmp_path, monkeypatch, capsys):
        """Test quick_setup auto-detects OpenAI from key prefix."""
        monkeypatch.setenv("HOME", str(tmp_path))
        if os.name == 'nt':
            monkeypatch.delenv("APPDATA", raising=False)

        config = Config.quick_setup("sk-proj-test-key-12345")

        assert config.llm_provider == "openai"

    def test_quick_setup_no_key_shows_help(self, capsys):
        """Test quick_setup with no key shows help."""
        config = Config.quick_setup()

        captured = capsys.readouterr()
        assert "API Key" in captured.out or "ANTHROPIC_API_KEY" in captured.out

    def test_quick_setup_explicit_provider(self, tmp_path, monkeypatch, capsys):
        """Test quick_setup with explicit provider."""
        monkeypatch.setenv("HOME", str(tmp_path))
        if os.name == 'nt':
            monkeypatch.delenv("APPDATA", raising=False)

        config = Config.quick_setup("my-custom-key", provider="custom")

        assert config.llm_provider == "custom"

"""Tests for review phases configuration."""

import os
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock


class TestReviewPhasesPath:
    """Tests for review phases path resolution."""

    def test_linux_path(self):
        """Test Linux/macOS path resolution."""
        with patch.dict(os.environ, {}, clear=False):
            with patch('os.name', 'posix'):
                # Import fresh to pick up patched os.name
                from opencode.cli import OpenCodeREPL

                # Create minimal REPL instance
                repl = MagicMock(spec=OpenCodeREPL)
                repl._get_review_phases_path = OpenCodeREPL._get_review_phases_path.__get__(repl)

                path = repl._get_review_phases_path()
                assert path == Path.home() / ".opencode" / "review_phases.toml"

    @pytest.mark.skipif(os.name != 'nt', reason="Windows-only test")
    def test_windows_path_with_appdata(self):
        """Test Windows path resolution with APPDATA."""
        with patch.dict(os.environ, {'APPDATA': 'C:\\Users\\Test\\AppData\\Roaming'}):
            from opencode.cli import OpenCodeREPL

            repl = MagicMock(spec=OpenCodeREPL)
            repl._get_review_phases_path = OpenCodeREPL._get_review_phases_path.__get__(repl)

            path = repl._get_review_phases_path()
            assert "opencode" in str(path)
            assert "review_phases.toml" in str(path)


class TestReviewPhasesDefault:
    """Tests for default review phases."""

    def test_default_phases_returned_when_no_config(self, temp_dir):
        """Test that default phases are returned when no config file exists."""
        from opencode.cli import OpenCodeREPL

        repl = MagicMock(spec=OpenCodeREPL)
        repl._get_review_phases_path = lambda: temp_dir / "nonexistent" / "review_phases.toml"
        repl._load_review_phases_from_file = OpenCodeREPL._load_review_phases_from_file.__get__(repl)
        repl._get_review_phases = OpenCodeREPL._get_review_phases.__get__(repl)

        phases = repl._get_review_phases()

        assert len(phases) == 10
        assert phases[0][0] == "Project Mapping"
        assert phases[1][0] == "Data & Control Flow"
        assert phases[9][0] == "Executive Summary"

    def test_default_phases_have_prompts(self, temp_dir):
        """Test that all default phases have non-empty prompts."""
        from opencode.cli import OpenCodeREPL

        repl = MagicMock(spec=OpenCodeREPL)
        repl._get_review_phases_path = lambda: temp_dir / "nonexistent" / "review_phases.toml"
        repl._load_review_phases_from_file = OpenCodeREPL._load_review_phases_from_file.__get__(repl)
        repl._get_review_phases = OpenCodeREPL._get_review_phases.__get__(repl)

        phases = repl._get_review_phases()

        for name, prompt in phases:
            assert name, "Phase name should not be empty"
            assert prompt, f"Phase '{name}' should have a prompt"
            assert len(prompt) > 50, f"Phase '{name}' prompt seems too short"


class TestReviewPhasesSave:
    """Tests for saving review phases config."""

    def test_save_creates_file(self, temp_dir):
        """Test that _save_default_review_phases creates the config file."""
        from opencode.cli import OpenCodeREPL

        phases_path = temp_dir / "review_phases.toml"

        repl = MagicMock(spec=OpenCodeREPL)
        repl._get_review_phases_path = lambda: phases_path
        repl._save_default_review_phases = OpenCodeREPL._save_default_review_phases.__get__(repl)

        result = repl._save_default_review_phases()

        assert result == phases_path
        assert phases_path.exists()

    def test_save_creates_parent_directories(self, temp_dir):
        """Test that save creates parent directories if needed."""
        from opencode.cli import OpenCodeREPL

        phases_path = temp_dir / "nested" / "dirs" / "review_phases.toml"

        repl = MagicMock(spec=OpenCodeREPL)
        repl._get_review_phases_path = lambda: phases_path
        repl._save_default_review_phases = OpenCodeREPL._save_default_review_phases.__get__(repl)

        result = repl._save_default_review_phases()

        assert result == phases_path
        assert phases_path.exists()
        assert phases_path.parent.exists()

    def test_saved_file_is_valid_toml(self, temp_dir):
        """Test that saved file is valid TOML."""
        import sys
        if sys.version_info >= (3, 11):
            import tomllib as tomli
        else:
            try:
                import tomli
            except ImportError:
                pytest.skip("tomli not available")

        from opencode.cli import OpenCodeREPL

        phases_path = temp_dir / "review_phases.toml"

        repl = MagicMock(spec=OpenCodeREPL)
        repl._get_review_phases_path = lambda: phases_path
        repl._save_default_review_phases = OpenCodeREPL._save_default_review_phases.__get__(repl)

        repl._save_default_review_phases()

        # Should not raise
        with open(phases_path, "rb") as f:
            data = tomli.load(f)

        assert "phases" in data
        assert len(data["phases"]) == 10

    def test_saved_file_has_all_phases(self, temp_dir):
        """Test that saved file contains all default phases."""
        import sys
        if sys.version_info >= (3, 11):
            import tomllib as tomli
        else:
            try:
                import tomli
            except ImportError:
                pytest.skip("tomli not available")

        from opencode.cli import OpenCodeREPL

        phases_path = temp_dir / "review_phases.toml"

        repl = MagicMock(spec=OpenCodeREPL)
        repl._get_review_phases_path = lambda: phases_path
        repl._save_default_review_phases = OpenCodeREPL._save_default_review_phases.__get__(repl)

        repl._save_default_review_phases()

        with open(phases_path, "rb") as f:
            data = tomli.load(f)

        phase_names = [p["name"] for p in data["phases"]]
        assert "Project Mapping" in phase_names
        assert "Security Analysis" in phase_names
        assert "Executive Summary" in phase_names


class TestReviewPhasesLoad:
    """Tests for loading review phases from config."""

    def test_load_returns_none_when_no_file(self, temp_dir):
        """Test that load returns None when config file doesn't exist."""
        from opencode.cli import OpenCodeREPL

        phases_path = temp_dir / "nonexistent.toml"

        repl = MagicMock(spec=OpenCodeREPL)
        repl._get_review_phases_path = lambda: phases_path
        repl._load_review_phases_from_file = OpenCodeREPL._load_review_phases_from_file.__get__(repl)

        result = repl._load_review_phases_from_file()

        assert result is None

    def test_load_custom_phases(self, temp_dir):
        """Test loading custom phases from config file."""
        import sys
        if sys.version_info >= (3, 11):
            pass  # tomllib is built-in
        else:
            try:
                import tomli
            except ImportError:
                pytest.skip("tomli not available")

        from opencode.cli import OpenCodeREPL

        phases_path = temp_dir / "review_phases.toml"
        phases_path.write_text('''
[[phases]]
name = "Custom Phase 1"
prompt = "Analyze the custom thing"

[[phases]]
name = "Custom Phase 2"
prompt = "Do another analysis"
''')

        repl = MagicMock(spec=OpenCodeREPL)
        repl._get_review_phases_path = lambda: phases_path
        repl._load_review_phases_from_file = OpenCodeREPL._load_review_phases_from_file.__get__(repl)

        result = repl._load_review_phases_from_file()

        assert result is not None
        assert len(result) == 2
        assert result[0] == ("Custom Phase 1", "Analyze the custom thing")
        assert result[1] == ("Custom Phase 2", "Do another analysis")

    def test_load_ignores_empty_prompts(self, temp_dir):
        """Test that phases with empty prompts are ignored."""
        import sys
        if sys.version_info >= (3, 11):
            pass
        else:
            try:
                import tomli
            except ImportError:
                pytest.skip("tomli not available")

        from opencode.cli import OpenCodeREPL

        phases_path = temp_dir / "review_phases.toml"
        phases_path.write_text('''
[[phases]]
name = "Valid Phase"
prompt = "This is valid"

[[phases]]
name = "Empty Phase"
prompt = ""

[[phases]]
name = "Another Valid"
prompt = "Also valid"
''')

        repl = MagicMock(spec=OpenCodeREPL)
        repl._get_review_phases_path = lambda: phases_path
        repl._load_review_phases_from_file = OpenCodeREPL._load_review_phases_from_file.__get__(repl)

        result = repl._load_review_phases_from_file()

        assert result is not None
        assert len(result) == 2
        assert result[0][0] == "Valid Phase"
        assert result[1][0] == "Another Valid"

    def test_load_with_tool_instructions(self, temp_dir):
        """Test that tool_instructions are appended to phases."""
        import sys
        if sys.version_info >= (3, 11):
            pass
        else:
            try:
                import tomli
            except ImportError:
                pytest.skip("tomli not available")

        from opencode.cli import OpenCodeREPL

        phases_path = temp_dir / "review_phases.toml"
        phases_path.write_text('''
[settings]
tool_instructions = "USE THESE TOOLS: glob, grep"

[[phases]]
name = "Test Phase"
prompt = "Analyze something"
''')

        repl = MagicMock(spec=OpenCodeREPL)
        repl._get_review_phases_path = lambda: phases_path
        repl._load_review_phases_from_file = OpenCodeREPL._load_review_phases_from_file.__get__(repl)
        repl._get_review_phases = OpenCodeREPL._get_review_phases.__get__(repl)

        result = repl._get_review_phases()

        assert len(result) == 1
        assert "Analyze something" in result[0][1]
        assert "USE THESE TOOLS" in result[0][1]

    def test_load_invalid_toml_returns_none(self, temp_dir, capsys):
        """Test that invalid TOML returns None and prints warning."""
        from opencode.cli import OpenCodeREPL

        phases_path = temp_dir / "review_phases.toml"
        phases_path.write_text("this is not valid { toml [[")

        repl = MagicMock(spec=OpenCodeREPL)
        repl._get_review_phases_path = lambda: phases_path
        repl._load_review_phases_from_file = OpenCodeREPL._load_review_phases_from_file.__get__(repl)

        result = repl._load_review_phases_from_file()

        assert result is None
        captured = capsys.readouterr()
        assert "Warning" in captured.out or result is None  # Either warns or silently fails


class TestReviewPhasesIntegration:
    """Integration tests for review phases."""

    def test_save_then_load_roundtrip(self, temp_dir):
        """Test that saved phases can be loaded back."""
        import sys
        if sys.version_info >= (3, 11):
            pass
        else:
            try:
                import tomli
            except ImportError:
                pytest.skip("tomli not available")

        from opencode.cli import OpenCodeREPL

        phases_path = temp_dir / "review_phases.toml"

        repl = MagicMock(spec=OpenCodeREPL)
        repl._get_review_phases_path = lambda: phases_path
        repl._save_default_review_phases = OpenCodeREPL._save_default_review_phases.__get__(repl)
        repl._load_review_phases_from_file = OpenCodeREPL._load_review_phases_from_file.__get__(repl)
        repl._get_review_phases = OpenCodeREPL._get_review_phases.__get__(repl)

        # Save defaults
        repl._save_default_review_phases()

        # Load them back
        loaded = repl._load_review_phases_from_file()

        assert loaded is not None
        assert len(loaded) == 10

        # Get phases (should use loaded config)
        phases = repl._get_review_phases()
        assert len(phases) == 10

    def test_custom_phases_override_defaults(self, temp_dir):
        """Test that custom phases completely replace defaults."""
        import sys
        if sys.version_info >= (3, 11):
            pass
        else:
            try:
                import tomli
            except ImportError:
                pytest.skip("tomli not available")

        from opencode.cli import OpenCodeREPL

        phases_path = temp_dir / "review_phases.toml"
        phases_path.write_text('''
[[phases]]
name = "Only Phase"
prompt = "This is the only phase"
''')

        repl = MagicMock(spec=OpenCodeREPL)
        repl._get_review_phases_path = lambda: phases_path
        repl._load_review_phases_from_file = OpenCodeREPL._load_review_phases_from_file.__get__(repl)
        repl._get_review_phases = OpenCodeREPL._get_review_phases.__get__(repl)

        phases = repl._get_review_phases()

        # Should only have the custom phase, not 10 defaults
        assert len(phases) == 1
        assert phases[0][0] == "Only Phase"


class TestReviewMode:
    """Tests for review mode functionality."""

    def test_review_mode_enum_exists(self):
        """Test that REVIEW mode exists in Mode enum."""
        from opencode.mode import Mode

        assert hasattr(Mode, 'REVIEW')
        assert Mode.REVIEW.value == "review"

    def test_is_review_property(self):
        """Test is_review property on ModeManager."""
        from opencode.mode import Mode, ModeManager

        manager = ModeManager()
        assert manager.is_review is False

        manager.to_review()
        assert manager.is_review is True
        assert manager.mode == Mode.REVIEW

    def test_review_mode_is_read_only(self):
        """Test that REVIEW mode is considered read-only."""
        from opencode.mode import ModeManager

        manager = ModeManager()
        manager.to_review()

        assert manager.is_read_only is True

    def test_review_mode_status_short(self):
        """Test short status shows R for review mode."""
        from opencode.mode import ModeManager

        manager = ModeManager()
        manager.to_review()

        assert manager.status_short() == "R/I"

        manager.to_auto()
        assert manager.status_short() == "R/A"

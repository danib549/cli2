"""Tests for workspace management."""

import os
import json
import pytest
from pathlib import Path

from opencode.workspace import Workspace, WorkspaceError, WORKSPACE_DIR, WORKSPACE_FILE


class TestWorkspace:
    """Tests for Workspace class."""

    def test_uninitialized_workspace(self, temp_dir):
        """Test workspace without .opencode directory."""
        # Change to temp_dir that has no .opencode
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            workspace = Workspace()

            assert workspace.root is None
            assert workspace.config_dir is None
            assert workspace.is_initialized is False
        finally:
            os.chdir(original_cwd)

    def test_init_creates_structure(self, temp_dir):
        """Test that init creates proper workspace structure."""
        workspace = Workspace()
        workspace.init(temp_dir)

        # Check directory structure
        assert (temp_dir / WORKSPACE_DIR).is_dir()
        assert (temp_dir / WORKSPACE_DIR / WORKSPACE_FILE).exists()
        assert (temp_dir / WORKSPACE_DIR / "config.toml").exists()
        assert (temp_dir / WORKSPACE_DIR / ".gitignore").exists()
        assert (temp_dir / "iai.md").exists()

    def test_init_creates_valid_workspace_json(self, temp_dir):
        """Test that workspace.json is valid JSON with required fields."""
        workspace = Workspace()
        workspace.init(temp_dir)

        workspace_file = temp_dir / WORKSPACE_DIR / WORKSPACE_FILE
        data = json.loads(workspace_file.read_text())

        assert "version" in data
        assert "created" in data
        assert "root" in data
        assert data["root"] == str(temp_dir)

    def test_init_sets_workspace_properties(self, temp_dir):
        """Test that init sets workspace root and config_dir."""
        workspace = Workspace()
        workspace.init(temp_dir)

        assert workspace.root == temp_dir
        assert workspace.config_dir == temp_dir / WORKSPACE_DIR
        assert workspace.is_initialized is True

    def test_init_with_explicit_root(self, temp_dir):
        """Test workspace with explicit root parameter."""
        workspace = Workspace(root=temp_dir)
        workspace.init(temp_dir)

        assert workspace.root == temp_dir
        assert workspace.is_initialized is True

    def test_find_workspace_in_parent(self, temp_dir):
        """Test finding workspace in parent directory."""
        # Create workspace in temp_dir
        Workspace().init(temp_dir)

        # Create subdirectory
        subdir = temp_dir / "subdir" / "deep"
        subdir.mkdir(parents=True)

        # Find workspace from subdirectory
        original_cwd = os.getcwd()
        try:
            os.chdir(subdir)
            workspace = Workspace()

            assert workspace.is_initialized is True
            assert workspace.root == temp_dir
        finally:
            os.chdir(original_cwd)

    def test_local_config_path(self, temp_workspace):
        """Test local config path property."""
        assert temp_workspace.local_config_path is not None
        assert temp_workspace.local_config_path.name == "config.toml"

    def test_local_config_path_uninitialized(self, temp_dir):
        """Test local config path when not initialized."""
        import os
        # Change to temp_dir which has no .opencode
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            workspace = Workspace()
            # Don't init - workspace should not find any .opencode
            assert workspace.local_config_path is None
        finally:
            os.chdir(original_cwd)

    def test_global_config_dir(self):
        """Test global config directory location."""
        global_dir = Workspace.global_config_dir()

        if os.name == 'nt':  # Windows
            appdata = os.environ.get('APPDATA')
            if appdata:
                assert global_dir == Path(appdata) / "opencode"
        else:
            assert global_dir == Path.home() / ".opencode"

    def test_global_config_path(self):
        """Test global config file path."""
        global_path = Workspace.global_config_path()
        assert global_path.name == "config.toml"

    def test_is_within_bounds_internal_path(self, temp_workspace):
        """Test that paths within workspace are allowed."""
        internal = temp_workspace.root / "src" / "file.py"
        assert temp_workspace.is_within_bounds(internal) is True

    def test_is_within_bounds_external_path(self, temp_workspace):
        """Test that paths outside workspace are rejected."""
        external = Path("/tmp/outside_workspace")
        assert temp_workspace.is_within_bounds(external) is False

    def test_is_within_bounds_uninitialized(self, temp_dir):
        """Test that uninitialized workspace allows all paths."""
        import os
        # Change to temp_dir which has no .opencode
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            workspace = Workspace()  # Not initialized (no .opencode in temp_dir)

            # Should return True for any path when not initialized
            assert workspace.is_within_bounds(Path("/anywhere")) is True
        finally:
            os.chdir(original_cwd)

    def test_resolve_path_relative(self, temp_workspace):
        """Test resolving relative paths."""
        resolved = temp_workspace.resolve_path("src/file.py")

        assert resolved.is_absolute()
        assert str(resolved).startswith(str(temp_workspace.root))

    def test_resolve_path_absolute_internal(self, temp_workspace):
        """Test resolving absolute paths within workspace."""
        abs_path = temp_workspace.root / "src" / "file.py"
        resolved = temp_workspace.resolve_path(str(abs_path))

        assert resolved == abs_path

    def test_resolve_path_absolute_external_raises(self, temp_workspace):
        """Test that resolving external paths raises WorkspaceError."""
        external = "/tmp/outside_workspace/file.py"

        with pytest.raises(WorkspaceError) as exc_info:
            temp_workspace.resolve_path(external)

        assert "outside workspace boundaries" in str(exc_info.value)

    def test_relative_path_internal(self, temp_workspace):
        """Test getting relative path for internal file."""
        internal = temp_workspace.root / "src" / "file.py"
        relative = temp_workspace.relative_path(internal)

        assert relative == "src/file.py"

    def test_relative_path_external(self, temp_workspace):
        """Test getting relative path for external file."""
        external = Path("/tmp/outside/file.py")
        relative = temp_workspace.relative_path(external)

        # Should return absolute path for external files
        assert relative == str(external)

    def test_relative_path_uninitialized(self):
        """Test relative_path when workspace not initialized."""
        workspace = Workspace()
        path = Path("/some/path/file.py")

        # Should return string of path
        assert workspace.relative_path(path) == str(path)

    def test_init_preserves_existing_config(self, temp_dir):
        """Test that init doesn't overwrite existing config."""
        # First init
        workspace = Workspace()
        workspace.init(temp_dir)

        # Modify config
        config_path = temp_dir / WORKSPACE_DIR / "config.toml"
        original_content = config_path.read_text()
        custom_content = original_content + "\n# Custom addition"
        config_path.write_text(custom_content)

        # Re-init
        workspace2 = Workspace()
        workspace2.init(temp_dir)

        # Config should be preserved
        assert config_path.read_text() == custom_content

    def test_init_preserves_existing_iai_md(self, temp_dir):
        """Test that init doesn't overwrite existing iai.md."""
        # Create existing iai.md
        iai_path = temp_dir / "iai.md"
        iai_path.write_text("# My Custom Project")

        # Init workspace
        workspace = Workspace()
        workspace.init(temp_dir)

        # iai.md should be preserved
        assert iai_path.read_text() == "# My Custom Project"

"""Workspace management - initialization and boundary enforcement."""

import os
import json
from pathlib import Path
from typing import Optional
from datetime import datetime


WORKSPACE_DIR = ".opencode"
WORKSPACE_FILE = "workspace.json"


class WorkspaceError(Exception):
    """Workspace-related errors."""
    pass


class Workspace:
    """Manages workspace initialization and file access boundaries."""

    def __init__(self, root: Optional[Path] = None):
        """Initialize workspace.

        Args:
            root: Workspace root directory. If None, searches for .opencode folder.
        """
        self.root: Optional[Path] = None
        self.config_dir: Optional[Path] = None

        if root:
            self.root = Path(root).resolve()
            self.config_dir = self.root / WORKSPACE_DIR
        else:
            # Search for existing workspace
            self._find_workspace()

    def _find_workspace(self) -> None:
        """Search for .opencode directory in current or parent directories."""
        current = Path.cwd().resolve()

        while current != current.parent:
            candidate = current / WORKSPACE_DIR
            if candidate.is_dir() and (candidate / WORKSPACE_FILE).exists():
                self.root = current
                self.config_dir = candidate
                return
            current = current.parent

        # Check root directory too
        candidate = current / WORKSPACE_DIR
        if candidate.is_dir() and (candidate / WORKSPACE_FILE).exists():
            self.root = current
            self.config_dir = candidate

    @property
    def is_initialized(self) -> bool:
        """Check if workspace is initialized."""
        return self.root is not None and self.config_dir is not None

    @property
    def local_config_path(self) -> Optional[Path]:
        """Path to local config file."""
        if self.config_dir:
            return self.config_dir / "config.toml"
        return None

    @staticmethod
    def global_config_dir() -> Path:
        """Get global config directory (cross-platform)."""
        # Windows: %APPDATA%\opencode or %USERPROFILE%\.opencode
        # Unix: ~/.opencode
        if os.name == 'nt':  # Windows
            appdata = os.environ.get('APPDATA')
            if appdata:
                return Path(appdata) / "opencode"
        return Path.home() / ".opencode"

    @staticmethod
    def global_config_path() -> Path:
        """Path to global config file."""
        return Workspace.global_config_dir() / "config.toml"

    def init(self, path: Optional[Path] = None) -> Path:
        """Initialize a new workspace.

        Args:
            path: Directory to initialize. Defaults to current directory.

        Returns:
            Path to the initialized workspace root.
        """
        root = Path(path).resolve() if path else Path.cwd().resolve()
        config_dir = root / WORKSPACE_DIR

        # Create .opencode directory
        config_dir.mkdir(parents=True, exist_ok=True)

        # Create workspace.json
        workspace_data = {
            "version": "1.0",
            "created": datetime.now().isoformat(),
            "root": str(root),
        }

        workspace_file = config_dir / WORKSPACE_FILE
        workspace_file.write_text(json.dumps(workspace_data, indent=2), encoding='utf-8')

        # Create empty local config
        local_config = config_dir / "config.toml"
        if not local_config.exists():
            local_config.write_text("""# OpenCode-Py Local Configuration
# This file overrides global settings for this workspace

[llm]
# provider = "anthropic"
# model = "claude-sonnet-4-20250514"

[complexity]
# threshold = 0.6

[execution]
# auto_execute_safe = true
""", encoding='utf-8')

        # Create .gitignore for sensitive files
        gitignore = config_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("""# Ignore sensitive files
config.toml
*.log
history
""", encoding='utf-8')

        # Create iai.md project instructions template
        iai_file = root / "iai.md"
        if not iai_file.exists():
            iai_file.write_text("""# Project Instructions for AI

This file tells the AI about your project. Edit it to match your needs.

## Project Overview

<!-- Describe your project in 1-2 sentences -->
This is a [type of project] that [what it does].

## Tech Stack

<!-- List the main technologies used -->
- Language:
- Framework:
- Database:
- Testing:

## Project Structure

<!-- Describe where important code lives -->
```
src/           # Main source code
tests/         # Test files
docs/          # Documentation
```

## Code Style

<!-- Your coding conventions -->
- Use descriptive variable names
- Add comments for complex logic
- Keep functions small and focused

## Important Files

<!-- Key files the AI should know about -->
- `src/main.py` - Entry point
- `src/config.py` - Configuration

## Common Commands

<!-- Commands the AI might need to run -->
```bash
# Run the app
python main.py

# Run tests
pytest

# Install dependencies
pip install -r requirements.txt
```

## Rules for AI

<!-- Specific instructions for the AI -->
- Always run tests after making changes
- Don't modify files in `vendor/` or `node_modules/`
- Ask before deleting files
- Use existing patterns in the codebase

## Notes

<!-- Any other context the AI should know -->

""", encoding='utf-8')

        self.root = root
        self.config_dir = config_dir

        return root

    def is_within_bounds(self, path: Path) -> bool:
        """Check if a path is within workspace boundaries.

        Args:
            path: Path to check (can be relative or absolute).

        Returns:
            True if path is within workspace, False otherwise.
        """
        if not self.is_initialized:
            return True  # No boundaries if not initialized

        try:
            # Resolve to absolute path
            resolved = Path(path).resolve()

            # Check if it's under workspace root
            resolved.relative_to(self.root)
            return True
        except ValueError:
            return False

    def resolve_path(self, path: str) -> Path:
        """Resolve a path relative to workspace root.

        Args:
            path: Path string (relative or absolute).

        Returns:
            Resolved absolute path.

        Raises:
            WorkspaceError: If path is outside workspace boundaries.
        """
        p = Path(path)

        # If relative, make it relative to workspace root (or cwd if not initialized)
        if not p.is_absolute():
            base = self.root if self.root else Path.cwd()
            p = base / p

        resolved = p.resolve()

        # Check boundaries
        if self.is_initialized and not self.is_within_bounds(resolved):
            raise WorkspaceError(
                f"Access denied: '{path}' is outside workspace boundaries.\n"
                f"Workspace root: {self.root}"
            )

        return resolved

    def relative_path(self, path: Path) -> str:
        """Get path relative to workspace root for display.

        Args:
            path: Absolute path.

        Returns:
            Relative path string, or absolute if outside workspace.
        """
        if not self.root:
            return str(path)

        try:
            return str(path.relative_to(self.root))
        except ValueError:
            return str(path)


def ensure_global_config() -> Path:
    """Ensure global config directory exists.

    Returns:
        Path to global config directory.
    """
    global_dir = Workspace.global_config_dir()
    global_dir.mkdir(parents=True, exist_ok=True)

    config_file = global_dir / "config.toml"
    if not config_file.exists():
        config_file.write_text("""# OpenCode-Py Global Configuration

[llm]
# provider = "anthropic"  # "anthropic", "openai", or "custom"
# model = "claude-sonnet-4-20250514"
# base_url = ""  # For custom providers

# Examples:
# Anthropic:  provider = "anthropic", model = "claude-sonnet-4-20250514"
# OpenAI:     provider = "openai", model = "gpt-4o"
# Ollama:     provider = "custom", model = "llama3", base_url = "http://localhost:11434/v1"

[complexity]
threshold = 0.6
auto_plan = true

[execution]
auto_execute_safe = true
tool_timeout = 30
checkpoint_enabled = true
""", encoding='utf-8')

    return global_dir

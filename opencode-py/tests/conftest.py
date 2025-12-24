"""Pytest fixtures for OpenCode-Py tests."""

import os
import pytest
from pathlib import Path
from tempfile import TemporaryDirectory


@pytest.fixture
def temp_dir():
    """Create a temporary directory for tests."""
    with TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_workspace(temp_dir):
    """Create a temporary workspace with .opencode directory."""
    from opencode.workspace import Workspace

    workspace = Workspace(root=temp_dir)
    workspace.init(temp_dir)
    return workspace


@pytest.fixture
def sample_file(temp_dir):
    """Create a sample Python file for testing."""
    file_path = temp_dir / "sample.py"
    content = """def hello():
    print("Hello, World!")

class Greeter:
    def greet(self, name):
        return f"Hello, {name}!"

if __name__ == "__main__":
    hello()
"""
    file_path.write_text(content)
    return file_path


@pytest.fixture
def large_file(temp_dir):
    """Create a large file (>500 lines) for testing."""
    file_path = temp_dir / "large_file.py"
    lines = []
    for i in range(600):
        lines.append(f"# Line {i + 1}")
        if i % 10 == 0:
            lines.append(f"def function_{i}():")
            lines.append(f"    pass")
    file_path.write_text("\n".join(lines))
    return file_path


@pytest.fixture
def config_file(temp_dir):
    """Create a sample config.toml file."""
    config_path = temp_dir / "config.toml"
    content = """[llm]
provider = "anthropic"
model = "claude-sonnet-4-20250514"

[complexity]
threshold = 0.7
auto_plan = true

[execution]
auto_execute_safe = true
tool_timeout = 60
"""
    config_path.write_text(content)
    return config_path


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Clean environment variables that might affect tests."""
    env_vars = [
        "OPENCODE_API_KEY",
        "OPENCODE_LLM_PROVIDER",
        "OPENCODE_LLM_MODEL",
        "OPENCODE_BASE_URL",
        "OPENCODE_COMPLEXITY_THRESHOLD",
    ]
    for var in env_vars:
        monkeypatch.delenv(var, raising=False)

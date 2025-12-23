"""Git checkpoint management."""

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class CheckpointResult:
    """Result of a checkpoint operation."""
    success: bool
    commit_hash: str = ""
    message: str = ""
    error: str = ""


class GitCheckpoint:
    """Manages git-based checkpoints for undo/redo functionality."""

    CHECKPOINT_PREFIX = "[opencode-checkpoint]"

    def __init__(self, repo_path: Optional[Path] = None):
        self.repo_path = repo_path or Path.cwd()

    def is_git_repo(self) -> bool:
        """Check if current directory is a git repository."""
        git_dir = self.repo_path / ".git"
        return git_dir.exists()

    def init_repo(self) -> CheckpointResult:
        """Initialize a git repository if one doesn't exist."""
        if self.is_git_repo():
            return CheckpointResult(True, message="Repository already exists")

        result = self._run_git("init")
        if result.returncode != 0:
            return CheckpointResult(False, error=result.stderr)

        return CheckpointResult(True, message="Initialized git repository")

    def has_changes(self) -> bool:
        """Check if there are uncommitted changes."""
        result = self._run_git("status", "--porcelain")
        return bool(result.stdout.strip())

    def create_checkpoint(self, description: str = "") -> CheckpointResult:
        """
        Create a checkpoint commit.

        Args:
            description: Human-readable description of what's being checkpointed.
        """
        if not self.is_git_repo():
            init_result = self.init_repo()
            if not init_result.success:
                return init_result

        if not self.has_changes():
            return CheckpointResult(
                True,
                message="No changes to checkpoint"
            )

        # Stage all changes
        add_result = self._run_git("add", "-A")
        if add_result.returncode != 0:
            return CheckpointResult(False, error=add_result.stderr)

        # Create commit
        commit_msg = f"{self.CHECKPOINT_PREFIX} {description}"
        commit_result = self._run_git("commit", "-m", commit_msg)
        if commit_result.returncode != 0:
            return CheckpointResult(False, error=commit_result.stderr)

        # Get commit hash
        hash_result = self._run_git("rev-parse", "--short", "HEAD")
        commit_hash = hash_result.stdout.strip()

        return CheckpointResult(
            True,
            commit_hash=commit_hash,
            message=f"Checkpoint created: {commit_hash}"
        )

    def list_checkpoints(self, limit: int = 10) -> list[dict]:
        """List recent checkpoints."""
        result = self._run_git(
            "log",
            f"--grep={self.CHECKPOINT_PREFIX}",
            f"-n{limit}",
            "--pretty=format:%h|%s|%cr"
        )

        if result.returncode != 0:
            return []

        checkpoints = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split("|")
            if len(parts) >= 3:
                checkpoints.append({
                    "hash": parts[0],
                    "message": parts[1].replace(self.CHECKPOINT_PREFIX, "").strip(),
                    "time": parts[2]
                })

        return checkpoints

    def restore_checkpoint(self, commit_hash: str) -> CheckpointResult:
        """
        Restore to a specific checkpoint.

        Args:
            commit_hash: The commit hash to restore to.
        """
        # First, create a checkpoint of current state
        if self.has_changes():
            self.create_checkpoint("Before restore")

        result = self._run_git("checkout", commit_hash, "--", ".")
        if result.returncode != 0:
            return CheckpointResult(False, error=result.stderr)

        return CheckpointResult(
            True,
            commit_hash=commit_hash,
            message=f"Restored to checkpoint {commit_hash}"
        )

    def _run_git(self, *args) -> subprocess.CompletedProcess:
        """Run a git command."""
        return subprocess.run(
            ["git", *args],
            cwd=self.repo_path,
            capture_output=True,
            text=True
        )


def create_checkpoint_fn(git: GitCheckpoint):
    """Factory function to create a checkpoint callback for tools."""
    def checkpoint(description: str) -> None:
        result = git.create_checkpoint(description)
        if not result.success and result.error:
            print(f"[checkpoint] Warning: {result.error}")
    return checkpoint

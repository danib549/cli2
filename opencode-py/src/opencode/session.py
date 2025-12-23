"""Session persistence - save and load conversation history."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

from opencode.llm.base import Message


@dataclass
class SessionMetadata:
    """Metadata about a saved session."""
    id: str
    name: str
    created_at: str
    updated_at: str
    message_count: int
    workspace: str
    summary: str = ""


class SessionManager:
    """Manage saving and loading of chat sessions."""

    def __init__(self, workspace_root: Path = None):
        """Initialize session manager.

        Args:
            workspace_root: Root of the workspace. Sessions are stored in .opencode/sessions/
        """
        self.workspace_root = workspace_root or Path.cwd()
        self.sessions_dir = self.workspace_root / ".opencode" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)

    def save(
        self,
        messages: list[Message],
        name: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Save a conversation to a session file.

        Args:
            messages: The conversation history to save.
            name: Optional human-readable name for the session.
            session_id: Optional existing session ID to overwrite.

        Returns:
            The session ID.
        """
        # Generate or use existing session ID
        if session_id:
            sid = session_id
        else:
            sid = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Generate name if not provided
        if not name:
            # Try to extract from first user message
            for msg in messages:
                if msg.role == "user" and msg.content:
                    name = msg.content[:50].strip()
                    if len(msg.content) > 50:
                        name += "..."
                    break
            if not name:
                name = f"Session {sid}"

        # Generate summary from conversation
        summary = self._generate_summary(messages)

        # Create metadata
        now = datetime.now().isoformat()
        metadata = SessionMetadata(
            id=sid,
            name=name,
            created_at=now,
            updated_at=now,
            message_count=len(messages),
            workspace=str(self.workspace_root),
            summary=summary,
        )

        # Check if updating existing session
        session_file = self.sessions_dir / f"{sid}.json"
        if session_file.exists():
            try:
                existing = json.loads(session_file.read_text())
                metadata.created_at = existing.get("metadata", {}).get("created_at", now)
            except Exception:
                pass

        # Save session
        session_data = {
            "metadata": asdict(metadata),
            "messages": [{"role": m.role, "content": m.content} for m in messages],
        }

        session_file.write_text(json.dumps(session_data, indent=2), encoding='utf-8')
        return sid

    def load(self, session_id: str) -> tuple[list[Message], SessionMetadata]:
        """Load a session by ID.

        Args:
            session_id: The session ID to load.

        Returns:
            Tuple of (messages, metadata).

        Raises:
            FileNotFoundError: If session doesn't exist.
        """
        session_file = self.sessions_dir / f"{session_id}.json"
        if not session_file.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

        data = json.loads(session_file.read_text(encoding='utf-8'))

        messages = [
            Message(role=m["role"], content=m["content"])
            for m in data.get("messages", [])
        ]

        meta_dict = data.get("metadata", {})
        metadata = SessionMetadata(
            id=meta_dict.get("id", session_id),
            name=meta_dict.get("name", ""),
            created_at=meta_dict.get("created_at", ""),
            updated_at=meta_dict.get("updated_at", ""),
            message_count=meta_dict.get("message_count", len(messages)),
            workspace=meta_dict.get("workspace", ""),
            summary=meta_dict.get("summary", ""),
        )

        return messages, metadata

    def list_sessions(self, limit: int = 20) -> list[SessionMetadata]:
        """List all saved sessions.

        Args:
            limit: Maximum number of sessions to return.

        Returns:
            List of session metadata, sorted by most recent first.
        """
        sessions = []

        for session_file in self.sessions_dir.glob("*.json"):
            try:
                data = json.loads(session_file.read_text(encoding='utf-8'))
                meta_dict = data.get("metadata", {})
                sessions.append(SessionMetadata(
                    id=meta_dict.get("id", session_file.stem),
                    name=meta_dict.get("name", ""),
                    created_at=meta_dict.get("created_at", ""),
                    updated_at=meta_dict.get("updated_at", ""),
                    message_count=meta_dict.get("message_count", 0),
                    workspace=meta_dict.get("workspace", ""),
                    summary=meta_dict.get("summary", ""),
                ))
            except Exception:
                continue

        # Sort by updated_at descending
        sessions.sort(key=lambda s: s.updated_at, reverse=True)
        return sessions[:limit]

    def delete(self, session_id: str) -> bool:
        """Delete a session.

        Args:
            session_id: The session ID to delete.

        Returns:
            True if deleted, False if not found.
        """
        session_file = self.sessions_dir / f"{session_id}.json"
        if session_file.exists():
            session_file.unlink()
            return True
        return False

    def get_latest(self) -> Optional[str]:
        """Get the ID of the most recently updated session.

        Returns:
            Session ID or None if no sessions exist.
        """
        sessions = self.list_sessions(limit=1)
        return sessions[0].id if sessions else None

    def _generate_summary(self, messages: list[Message], max_length: int = 100) -> str:
        """Generate a brief summary of the conversation.

        Args:
            messages: The conversation messages.
            max_length: Maximum length of the summary.

        Returns:
            A brief summary string.
        """
        # Collect user messages
        user_messages = [m.content for m in messages if m.role == "user" and m.content]

        if not user_messages:
            return ""

        # Use first and last user messages for context
        if len(user_messages) == 1:
            summary = user_messages[0]
        else:
            summary = f"{user_messages[0][:40]}... -> {user_messages[-1][:40]}"

        if len(summary) > max_length:
            summary = summary[:max_length - 3] + "..."

        return summary


def format_session_list(sessions: list[SessionMetadata]) -> str:
    """Format session list for display.

    Args:
        sessions: List of session metadata.

    Returns:
        Formatted string for display.
    """
    if not sessions:
        return "No saved sessions."

    lines = ["Saved sessions:", ""]

    for s in sessions:
        # Parse date for display
        try:
            dt = datetime.fromisoformat(s.updated_at)
            date_str = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            date_str = s.updated_at[:16] if s.updated_at else "unknown"

        lines.append(f"  [{s.id}] {s.name}")
        lines.append(f"       {date_str} | {s.message_count} messages")
        if s.summary:
            lines.append(f"       {s.summary[:60]}")
        lines.append("")

    return "\n".join(lines)

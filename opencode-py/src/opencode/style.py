"""Cross-platform terminal styling.

Provides simple text styling that works on all platforms.
Falls back to plain text markers when ANSI colors aren't supported.
"""

import os
import sys


def _supports_color() -> bool:
    """Check if the terminal supports ANSI colors."""
    # Disable colors if NO_COLOR env var is set
    if os.environ.get("NO_COLOR"):
        return False

    # Disable colors if not a TTY
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False

    # Check for Windows
    if os.name == "nt":
        # Windows 10+ supports ANSI, but we need to be conservative
        # Check for Windows Terminal, VS Code, or ConEmu
        if os.environ.get("WT_SESSION"):  # Windows Terminal
            return True
        if os.environ.get("TERM_PROGRAM") == "vscode":
            return True
        if os.environ.get("ConEmuANSI") == "ON":
            return True
        # Default: assume no color support on Windows CMD
        return False

    # Unix-like systems generally support colors
    return True


# Check once at import time
USE_COLOR = _supports_color()


def dim(text: str) -> str:
    """Dim/gray text."""
    if USE_COLOR:
        return f"\033[90m{text}\033[0m"
    return text


def bold(text: str) -> str:
    """Bold text."""
    if USE_COLOR:
        return f"\033[1m{text}\033[0m"
    return text


def green(text: str) -> str:
    """Green text (success)."""
    if USE_COLOR:
        return f"\033[32m{text}\033[0m"
    return f"+ {text}"


def red(text: str) -> str:
    """Red text (error)."""
    if USE_COLOR:
        return f"\033[31m{text}\033[0m"
    return f"! {text}"


def yellow(text: str) -> str:
    """Yellow text (warning)."""
    if USE_COLOR:
        return f"\033[33m{text}\033[0m"
    return f"* {text}"


def blue(text: str) -> str:
    """Blue text (info)."""
    if USE_COLOR:
        return f"\033[34m{text}\033[0m"
    return text


def cyan(text: str) -> str:
    """Cyan text (command)."""
    if USE_COLOR:
        return f"\033[36m{text}\033[0m"
    return f"$ {text}"


# Box drawing characters (ASCII fallback for Windows)
if USE_COLOR:
    BOX_TOP_LEFT = "┌"
    BOX_TOP_RIGHT = "┐"
    BOX_BOTTOM_LEFT = "└"
    BOX_BOTTOM_RIGHT = "┘"
    BOX_HORIZONTAL = "─"
    BOX_VERTICAL = "│"
    BOX_TEE = "├"
    BOX_TEE_RIGHT = "┤"
else:
    BOX_TOP_LEFT = "+"
    BOX_TOP_RIGHT = "+"
    BOX_BOTTOM_LEFT = "+"
    BOX_BOTTOM_RIGHT = "+"
    BOX_HORIZONTAL = "-"
    BOX_VERTICAL = "|"
    BOX_TEE = "+"
    BOX_TEE_RIGHT = "+"


def box(title: str, content: str, width: int = 60) -> str:
    """Create a simple box around content."""
    lines = []

    # Top border with title
    title_part = f" {title} " if title else ""
    remaining = width - len(title_part) - 2
    left_pad = remaining // 2
    right_pad = remaining - left_pad

    lines.append(
        BOX_TOP_LEFT +
        BOX_HORIZONTAL * left_pad +
        title_part +
        BOX_HORIZONTAL * right_pad +
        BOX_TOP_RIGHT
    )

    # Content
    for line in content.split("\n"):
        # Truncate if too long
        if len(line) > width - 4:
            line = line[:width - 7] + "..."
        padding = width - len(line) - 4
        lines.append(f"{BOX_VERTICAL}  {line}{' ' * padding}  {BOX_VERTICAL}")

    # Bottom border
    lines.append(BOX_BOTTOM_LEFT + BOX_HORIZONTAL * (width - 2) + BOX_BOTTOM_RIGHT)

    return "\n".join(lines)


def separator(char: str = "-", width: int = 60) -> str:
    """Create a separator line."""
    return char * width


def header(text: str) -> str:
    """Format a header/section title."""
    return f"\n{'=' * 3} {text} {'=' * 3}\n"


def bullet(text: str, indent: int = 0) -> str:
    """Format a bullet point."""
    prefix = "  " * indent
    return f"{prefix}- {text}"

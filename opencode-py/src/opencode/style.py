"""Cross-platform terminal styling.

Provides simple text styling that works on all platforms.
Falls back to plain text markers when ANSI colors aren't supported.
"""

import os
import sys


def _supports_color() -> bool:
    """Check if the terminal supports ANSI colors."""
    # Force colors with FORCE_COLOR env var
    if os.environ.get("FORCE_COLOR"):
        return True

    # Disable colors if NO_COLOR env var is set
    if os.environ.get("NO_COLOR"):
        return False

    # Disable colors if not a TTY
    if not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        return False

    # Check for Windows
    if os.name == "nt":
        # Windows 10+ supports ANSI in many terminals
        # Check for known good terminals
        if os.environ.get("WT_SESSION"):  # Windows Terminal
            return True
        if os.environ.get("TERM_PROGRAM") == "vscode":
            return True
        if os.environ.get("ConEmuANSI") == "ON":
            return True
        if os.environ.get("ANSICON"):  # ANSICON
            return True
        if os.environ.get("TERM"):  # Has TERM set (e.g., Git Bash, Cygwin)
            return True

        # Try to enable VT100 mode on Windows 10+
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            # Get stdout handle
            handle = kernel32.GetStdHandle(-11)  # STD_OUTPUT_HANDLE
            # Get current mode
            mode = ctypes.c_ulong()
            kernel32.GetConsoleMode(handle, ctypes.byref(mode))
            # Enable ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x0004)
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
            return True
        except Exception:
            pass

        # Default: assume no color support on older Windows CMD
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


def ai_response_start() -> str:
    """Visual marker for start of AI response."""
    if USE_COLOR:
        # Bold cyan with box drawing characters
        label = "\033[1;36m ASSISTANT \033[0m"
        line_left = f"\033[36m{'─' * 25}\033[0m"
        line_right = f"\033[36m{'─' * 24}\033[0m"
        return f"\n{line_left}{label}{line_right}"
    else:
        # ASCII fallback for Windows CMD
        return f"\n{'-' * 25} ASSISTANT {'-' * 24}"


def ai_response_end() -> str:
    """Visual marker for end of AI response."""
    if USE_COLOR:
        return f"\033[90m{'─' * 60}\033[0m\n"
    else:
        return f"{'-' * 60}\n"


def user_prompt_marker() -> str:
    """Visual marker before user prompt."""
    if USE_COLOR:
        label = "\033[1;32m YOU \033[0m"
        line_left = f"\033[32m{'─' * 28}\033[0m"
        line_right = f"\033[32m{'─' * 28}\033[0m"
        return f"\n{line_left}{label}{line_right}"
    else:
        return f"\n{'-' * 28} YOU {'-' * 28}"


def tool_output_marker(tool_name: str) -> str:
    """Visual marker for tool output."""
    tool_display = tool_name.upper()[:12]  # Limit length
    if USE_COLOR:
        label = f"\033[1;33m {tool_display} \033[0m"
        padding = 12 - len(tool_display)
        line_left = f"\033[33m{'─' * 20}\033[0m"
        line_right = f"\033[33m{'─' * (20 + padding)}\033[0m"
        return f"{line_left}{label}{line_right}"
    else:
        padding = 12 - len(tool_display)
        return f"{'-' * 20} {tool_display} {'-' * (20 + padding)}"


def section_header(title: str, style: str = "info") -> str:
    """Create a styled section header.

    Args:
        title: The section title
        style: One of "info", "success", "warning", "error"
    """
    colors = {
        "info": ("36", "1;36"),      # cyan
        "success": ("32", "1;32"),   # green
        "warning": ("33", "1;33"),   # yellow
        "error": ("31", "1;31"),     # red
    }

    line_color, title_color = colors.get(style, colors["info"])
    title_display = f" {title} "
    total_width = 60
    title_len = len(title_display)
    left_len = (total_width - title_len) // 2
    right_len = total_width - title_len - left_len

    if USE_COLOR:
        return (
            f"\033[{line_color}m{'─' * left_len}\033[0m"
            f"\033[{title_color}m{title_display}\033[0m"
            f"\033[{line_color}m{'─' * right_len}\033[0m"
        )
    else:
        return f"{'-' * left_len}{title_display}{'-' * right_len}"

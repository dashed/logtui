"""Utility functions for sentry-tui."""

import re
from rich.text import Text

from .constants import ANSI_ESCAPE_REGEX, SENTRY_SERVICE_COLORS


def strip_ansi_codes(text: str) -> str:
    """Strip ANSI color codes from text."""
    return ANSI_ESCAPE_REGEX.sub("", text)


def apply_rich_coloring(text: str) -> Text:
    """Apply Rich-based coloring to log text while stripping ANSI codes."""
    # Strip all ANSI codes first
    clean_text = strip_ansi_codes(text)

    # Create a Rich Text object
    rich_text = Text(clean_text)

    # Apply coloring based on content patterns
    if "server" in clean_text:
        # Purple color for server logs (matching Sentry's color scheme)
        rich_text.highlight_regex(r"\bserver\b", style="rgb(108,95,199)")
    elif "worker" in clean_text or "taskworker" in clean_text:
        # Yellow color for worker logs
        rich_text.highlight_regex(r"\b(worker|taskworker)\b", style="rgb(255,194,39)")
    elif "webpack" in clean_text:
        # Blue color for webpack logs
        rich_text.highlight_regex(r"\bwebpack\b", style="rgb(61,116,219)")
    elif "cron" in clean_text or "celery-beat" in clean_text:
        # Pink color for cron/beat logs
        rich_text.highlight_regex(r"\b(cron|celery-beat)\b", style="rgb(255,86,124)")
    elif "relay" in clean_text:
        # Red color for relay logs
        rich_text.highlight_regex(r"\brelay\b", style="rgb(250,71,71)")
    elif "getsentry-outcomes" in clean_text:
        # Orange color for outcomes logs
        rich_text.highlight_regex(r"\bgetsentry-outcomes\b", style="rgb(255,119,56)")

    # Apply log level coloring
    rich_text.highlight_regex(r"\[ERROR\]", style="bold red")
    rich_text.highlight_regex(r"\[WARNING\]", style="bold yellow")
    rich_text.highlight_regex(r"\[INFO\]", style="bold blue")
    rich_text.highlight_regex(r"\[DEBUG\]", style="bold dim")

    # Highlight timestamps
    rich_text.highlight_regex(r"\d{2}:\d{2}:\d{2}", style="dim")

    return rich_text


def strip_ansi_background_colors(text: str) -> str:
    """Strip ANSI background color codes while preserving foreground colors and formatting.
    
    This function removes background color codes (codes 40-49, 100-109) while keeping
    foreground colors and text formatting intact. This prevents color bleeding in the TUI
    while maintaining readable colored text.
    
    Args:
        text: Text potentially containing ANSI codes
        
    Returns:
        Text with background colors removed but foreground colors preserved
    """
    def replace_bg_codes(match):
        """Replace background color codes while preserving other codes."""
        full_code = match.group(0)
        # Extract the parameters between ESC[ and m
        params = full_code[2:-1]  # Remove ESC[ and m

        # Split by semicolon and filter out background codes
        parts = params.split(";")
        filtered_parts = []

        i = 0
        while i < len(parts):
            param = parts[i]

            # Check if this is a background color code
            if param.isdigit():
                num = int(param)
                # Standard background colors (40-47) or high intensity (100-107)
                if (40 <= num <= 47) or (100 <= num <= 107):
                    i += 1
                    continue
                # 256-color background (48;5;n)
                elif num == 48 and i + 2 < len(parts) and parts[i + 1] == "5":
                    i += 3  # Skip 48, 5, and the color number
                    continue
                # RGB background (48;2;r;g;b)
                elif num == 48 and i + 4 < len(parts) and parts[i + 1] == "2":
                    i += 5  # Skip 48, 2, r, g, b
                    continue

            filtered_parts.append(param)
            i += 1

        # If no codes remain, return empty string
        if not filtered_parts:
            return ""

        # Reconstruct the escape sequence
        return f"\x1b[{';'.join(filtered_parts)}m"
    
    # Apply the background color removal
    return ANSI_ESCAPE_REGEX.sub(replace_bg_codes, text)
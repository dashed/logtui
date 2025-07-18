"""Utility functions for sentry-tui."""

import re
from rich.text import Text

from .constants import ANSI_ESCAPE_REGEX, SENTRY_SERVICE_COLORS


def strip_ansi_codes(text: str) -> str:
    """Strip ANSI color codes from text."""
    return ANSI_ESCAPE_REGEX.sub("", text)


def apply_rich_coloring(text: str) -> Text:
    """Apply Rich-based coloring to replace ANSI codes with clean styling.
    
    This function strips ANSI codes and applies Rich-based coloring based on
    service detection and log level patterns. It provides cleaner, more reliable
    styling than raw ANSI codes while preserving the visual information.
    
    Args:
        text: Raw text with potential ANSI codes
        
    Returns:
        Rich Text object with clean styling applied
    """
    # First strip any existing ANSI codes
    clean_text = strip_ansi_codes(text)
    
    # Create Rich Text object
    rich_text = Text(clean_text)
    
    # Apply service-based coloring by detecting service names
    for service, color in SENTRY_SERVICE_COLORS.items():
        if service in clean_text.lower():
            # Find service name positions and apply color
            start = clean_text.lower().find(service)
            if start != -1:
                end = start + len(service)
                rich_text.stylize(color, start, end)
            break  # Only apply first matching service color
    
    # Apply log level based coloring
    clean_lower = clean_text.lower()
    if any(word in clean_lower for word in ["error", "exception", "traceback", "failed", "critical"]):
        rich_text.stylize("red bold")
    elif any(word in clean_lower for word in ["warning", "warn", "deprecated"]):
        rich_text.stylize("yellow")
    elif any(word in clean_lower for word in ["debug"]):
        rich_text.stylize("dim")
    
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
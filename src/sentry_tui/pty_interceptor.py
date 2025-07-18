#!/usr/bin/env python3
"""
PTY-based interception for capturing process output while preserving terminal behavior.
This implementation follows the approach outlined in the feasibility document.

This module has been refactored into separate modules for better maintainability:
- constants.py: Enums, regex patterns, and service colors
- utils.py: Utility functions for ANSI processing
- log_processing.py: LogLine class and log parsing
- process_monitor.py: Process monitoring and port detection
- ui_components.py: UI widgets and components
- pty_core.py: Core PTY functionality
- app.py: Main application class
"""

import sys

# Import all the main classes that users will need
from .app import SentryTUIApp
from .constants import ProcessState
from .log_processing import LogLine
from .pty_core import PTYInterceptor
from .ui_components import CommandEditScreen, ProcessStatusBar, ServiceToggleBar
from .utils import apply_rich_coloring, strip_ansi_codes, strip_ansi_background_colors

# Export the main classes for backward compatibility
__all__ = [
    "SentryTUIApp",
    "PTYInterceptor",
    "ProcessState",
    "LogLine",
    "ServiceToggleBar",
    "ProcessStatusBar",
    "CommandEditScreen",
    "strip_ansi_codes",
    "strip_ansi_background_colors",
    "apply_rich_coloring",
    "main",
]


def main():
    """Main entry point for the PTY interceptor."""
    if len(sys.argv) < 2:
        print("Usage: python -m sentry_tui.pty_interceptor <command> [args...]")
        print(
            "Example: python -m sentry_tui.pty_interceptor python -m sentry_tui.dummy_app"
        )
        print("Use --auto-restart to enable automatic restart on crashes")
        sys.exit(1)

    # Parse arguments
    auto_restart = False
    command_args = []
    for arg in sys.argv[1:]:
        if arg == "--auto-restart":
            auto_restart = True
        else:
            command_args.append(arg)

    if not command_args:
        print("Error: No command provided")
        sys.exit(1)

    app = SentryTUIApp(command_args, auto_restart=auto_restart)
    app.run()


if __name__ == "__main__":
    main()

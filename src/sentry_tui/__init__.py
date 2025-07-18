"""Sentry TUI - A terminal user interface for filtering Sentry devserver logs.

This package provides a Terminal User Interface for intercepting and filtering
Sentry devserver logs with features like service filtering, command editing,
process monitoring, and more.

Main components:
- SentryTUIApp: Main application class
- PTYInterceptor: Core PTY-based process interception
- UI components: Service toggles, status bars, command editor
- Process monitoring: Port detection, memory/CPU tracking
- Log processing: Parsing and filtering Sentry Honcho format logs
"""

import sys
import argparse
from typing import List, Optional

# Import main classes for easy access
from .app import SentryTUIApp
from .constants import ProcessState
from .log_processing import LogLine
from .pty_core import PTYInterceptor
from .ui_components import CommandEditScreen, ProcessStatusBar, ServiceToggleBar
from .utils import apply_rich_coloring, strip_ansi_codes, strip_ansi_background_colors

__version__ = "0.1.0"

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


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser."""
    parser = argparse.ArgumentParser(
        prog="sentry-tui",
        description="A TUI for intercepting and filtering Sentry devserver logs",
        epilog="Example: sentry-tui -- getsentry devserver --workers",
    )

    parser.add_argument(
        "command",
        nargs="+",
        help="Command to run and intercept (e.g., 'sentry devserver')",
    )

    parser.add_argument(
        "--auto-restart",
        action="store_true",
        help="Automatically restart the process if it crashes",
    )

    parser.add_argument(
        "--max-lines",
        type=int,
        default=10000,
        help="Maximum number of log lines to keep in memory (default: 10000)",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="%(prog)s 0.1.0",
    )

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Main CLI entry point."""
    parser = create_parser()
    args = parser.parse_args(argv)

    try:
        # Create and run the TUI application
        app = SentryTUIApp(
            command=args.command,
            auto_restart=args.auto_restart,
        )
        app.run()
        return 0
    except KeyboardInterrupt:
        # Handle Ctrl+C gracefully
        print("\nInterrupted by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())

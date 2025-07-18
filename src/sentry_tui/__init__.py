"""Sentry TUI - A terminal user interface for filtering Sentry devserver logs."""

import sys
import argparse
from typing import List, Optional

from .pty_interceptor import SentryTUIApp


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

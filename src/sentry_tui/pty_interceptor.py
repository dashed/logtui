#!/usr/bin/env python3
"""
PTY-based interception for capturing process output while preserving terminal behavior.
This implementation follows the approach outlined in the feasibility document.
"""

import pty
import os
import select
import subprocess
import sys
import signal
import threading
import time
import re
from typing import List, Callable, Optional
from textual.app import App, ComposeResult
from textual.widgets import RichLog, Input, Footer, Header
from textual.containers import Vertical
from textual.reactive import reactive
from textual.binding import Binding
from rich.text import Text


# Regex used for ansi escape code splitting
# Ref: https://github.com/chalk/ansi-regex/blob/f338e1814144efb950276aac84135ff86b72dc8e/index.js
# License: MIT by Sindre Sorhus <sindresorhus@gmail.com>
# Matches all ansi escape code sequences in a string
ANSI_ESCAPE_REGEX = re.compile(
    r"[\u001B\u009B][\[\]()#;?]*"
    r"(?:(?:(?:(?:;[-a-zA-Z\d\/#&.:=?%@~_]+)*"
    r"|[a-zA-Z\d]+(?:;[-a-zA-Z\d\/#&.:=?%@~_]*)*)?"
    r"(?:\u0007|\u001B\u005C|\u009C))"
    r"|(?:(?:\d{1,4}(?:;\d{0,4})*)?"
    r"[\dA-PR-TZcf-nq-uy=><~]))"
)


def strip_ansi_codes(text: str) -> str:
    """Remove all VT control characters. Use to estimate displayed string width."""
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
        rich_text.highlight_regex(r'\bserver\b', style="rgb(108,95,199)")
    elif "worker" in clean_text or "taskworker" in clean_text:
        # Yellow color for worker logs
        rich_text.highlight_regex(r'\b(worker|taskworker)\b', style="rgb(255,194,39)")
    elif "webpack" in clean_text:
        # Blue color for webpack logs
        rich_text.highlight_regex(r'\bwebpack\b', style="rgb(61,116,219)")
    elif "cron" in clean_text or "celery-beat" in clean_text:
        # Pink color for cron/beat logs
        rich_text.highlight_regex(r'\b(cron|celery-beat)\b', style="rgb(255,86,124)")
    elif "relay" in clean_text:
        # Red color for relay logs
        rich_text.highlight_regex(r'\brelay\b', style="rgb(250,71,71)")
    elif "getsentry-outcomes" in clean_text:
        # Orange color for outcomes logs
        rich_text.highlight_regex(r'\bgetsentry-outcomes\b', style="rgb(255,119,56)")
    
    # Apply log level coloring
    rich_text.highlight_regex(r'\[ERROR\]', style="bold red")
    rich_text.highlight_regex(r'\[WARNING\]', style="bold yellow")
    rich_text.highlight_regex(r'\[INFO\]', style="bold blue")
    rich_text.highlight_regex(r'\[DEBUG\]', style="bold dim")
    
    # Highlight timestamps
    rich_text.highlight_regex(r'\d{2}:\d{2}:\d{2}', style="dim")
    
    return rich_text


def strip_ansi_background_colors(text: str) -> str:
    """Remove ANSI background color codes while preserving foreground colors and other formatting."""
    # Pattern to match and remove background color codes while preserving other codes
    # This handles combined codes like ESC[31;42m (red foreground, green background)
    
    def replace_bg_codes(match):
        full_code = match.group(0)
        # Extract the parameters between ESC[ and m
        params = full_code[2:-1]  # Remove ESC[ and m
        
        # Split by semicolon and filter out background codes
        parts = params.split(';')
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
                elif num == 48 and i + 2 < len(parts) and parts[i + 1] == '5':
                    i += 3  # Skip 48, 5, and the color number
                    continue
                # RGB background (48;2;r;g;b)
                elif num == 48 and i + 4 < len(parts) and parts[i + 1] == '2':
                    i += 5  # Skip 48, 2, r, g, b
                    continue
            
            filtered_parts.append(param)
            i += 1
        
        # If no codes remain, return empty string
        if not filtered_parts:
            return ""
        
        # Reconstruct the escape sequence
        return f"\x1b[{';'.join(filtered_parts)}m"
    
    # Pattern to match any ANSI escape sequence
    pattern = re.compile(r'\x1b\[[0-9;]*m')
    return pattern.sub(replace_bg_codes, text)


# Sentry service colors from src/sentry/runner/formatting.py:18-24
SENTRY_SERVICE_COLORS = {
    "server": (108, 95, 199),
    "worker": (255, 194, 39),
    "webpack": (61, 116, 219),
    "cron": (255, 86, 124),
    "relay": (250, 71, 71),
    # Additional getsentry service from getsentry/conf/settings/dev.py:205
    "getsentry-outcomes": (255, 119, 56),  # Orange color for billing/outcomes
    "celery-beat": (255, 86, 124),  # Same as cron
    "taskworker": (255, 194, 39),  # Same as worker
}


class LogLine:
    """Represents a single log line with metadata."""

    def __init__(self, content: str, timestamp: Optional[float] = None):
        self.content = content
        self.timestamp = timestamp or time.time()
        self.service = self._extract_service()
        self.level = self._extract_level()
        self.module_name = self._extract_module_name()
        self.message = self._extract_message()

    def _extract_service(self) -> str:
        """Extract service name from Sentry SentryPrinter format.

        Format: {colored_service_name} {colored_indicator} HH:MM:SS [LEVEL] module.name: message

        The service name appears at the beginning with ANSI color codes.
        We need to strip ANSI codes and extract the service name.
        """
        # Remove ANSI color codes first
        clean_content = strip_ansi_codes(self.content)

        # Look for service name at the beginning, followed by space and timestamp
        # Pattern: "service_name HH:MM:SS [LEVEL] module.name: message"
        match = re.match(
            r"^\s*([a-zA-Z0-9_-]+)\s+\d{2}:\d{2}:\d{2}\s+\[", clean_content
        )
        if match:
            return match.group(1).strip()

        # Fallback: try to find service name in known services
        for service in SENTRY_SERVICE_COLORS.keys():
            if service in clean_content:
                return service

        return "unknown"

    def _extract_level(self) -> str:
        """Extract log level from HumanRenderer format: HH:MM:SS [LEVEL] module.name: message"""
        # Remove ANSI color codes first
        clean_content = strip_ansi_codes(self.content)

        # Look for [LEVEL] pattern
        match = re.search(
            r"\[(DEBUG|INFO|WARNING|ERROR|CRITICAL|FATAL)\]", clean_content
        )
        if match:
            return match.group(1)

        return "INFO"  # Default level

    def _extract_module_name(self) -> str:
        """Extract module name from HumanRenderer format: HH:MM:SS [LEVEL] module.name: message"""
        # Remove ANSI color codes first
        clean_content = strip_ansi_codes(self.content)

        # Look for pattern after [LEVEL]: module.name: message
        match = re.search(r"\[\w+\]\s+([^:]+):", clean_content)
        if match:
            return match.group(1).strip()

        return "root"  # Default module name

    def _extract_message(self) -> str:
        """Extract the actual log message from HumanRenderer format"""
        # Remove ANSI color codes first
        clean_content = strip_ansi_codes(self.content)

        # Look for message after module.name:
        match = re.search(r"\[\w+\]\s+[^:]+:\s*(.*)$", clean_content)
        if match:
            return match.group(1).strip()

        # Fallback: return content after first colon if any
        if ":" in clean_content:
            return clean_content.split(":", 1)[1].strip()

        return clean_content.strip()


class PTYInterceptor:
    """PTY-based process interceptor that captures output while preserving terminal behavior."""

    def __init__(
        self, command: List[str], on_output: Optional[Callable[[str], None]] = None
    ):
        self.command = command
        self.on_output = on_output or self._default_output_handler
        self.process = None
        self.master_fd = None
        self.slave_fd = None
        self.running = False
        self.output_thread = None
        self.buffer = ""

    def _default_output_handler(self, line: str):
        """Default output handler that prints to stdout."""
        print(line, end="")

    def start(self):
        """Start the PTY-based interception."""
        # Create a pseudo-terminal
        self.master_fd, self.slave_fd = pty.openpty()

        # Start the subprocess with PTY
        self.process = subprocess.Popen(
            self.command,
            stdin=self.slave_fd,
            stdout=self.slave_fd,
            stderr=self.slave_fd,
            start_new_session=True,
        )

        # Close the slave fd in the parent process
        os.close(self.slave_fd)

        # Set up non-blocking I/O
        import fcntl

        flags = fcntl.fcntl(self.master_fd, fcntl.F_GETFL)
        fcntl.fcntl(self.master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        self.running = True

        # Start output reading thread
        self.output_thread = threading.Thread(target=self._read_output, daemon=True)
        self.output_thread.start()

    def _read_output(self):
        """Read output from the PTY master in a separate thread."""
        while self.running:
            try:
                # Use select to check for available data
                ready, _, _ = select.select([self.master_fd], [], [], 0.1)
                if ready:
                    data = os.read(self.master_fd, 4096)
                    if data:
                        # Decode and process the data
                        text = data.decode("utf-8", errors="replace")
                        self._process_output(text)
                    else:
                        # EOF reached
                        break
            except (OSError, IOError):
                # Handle PTY closure or other I/O errors
                break

    def _process_output(self, text: str):
        """Process raw output text and extract complete lines."""
        self.buffer += text

        # Split into lines
        lines = self.buffer.split("\n")

        # Keep the last incomplete line in buffer
        self.buffer = lines[-1]

        # Process complete lines
        for line in lines[:-1]:
            self.on_output(line + "\n")

    def stop(self):
        """Stop the PTY interception."""
        self.running = False

        if self.process:
            try:
                # Send SIGTERM to process group
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)

                # Wait for process to terminate
                self.process.wait(timeout=5)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                # Force kill if necessary
                try:
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass

        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                # File descriptor was already closed
                pass
            finally:
                self.master_fd = None

        if self.output_thread and self.output_thread.is_alive():
            self.output_thread.join(timeout=1)


class SentryTUIApp(App):
    """Main TUI application for intercepting and filtering Sentry devserver logs."""

    CSS = """
    Screen {
        layers: base overlay;
    }
    
    #log_display {
        height: 1fr;
        border: solid $primary;
        scrollbar-gutter: stable;
        background: transparent;
    }
    
    #log_display:focus {
        background: transparent;
        background-tint: transparent;
    }
    
    #filter_input {
        height: 3;
        border: solid $accent;
        margin: 1;
    }
    
    #status_bar {
        height: 1;
        background: $surface;
        color: $text;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("f", "focus_filter", "Focus Filter"),
        Binding("l", "focus_log", "Focus Log"),
        Binding("c", "clear_logs", "Clear Logs"),
        Binding("p", "toggle_pause", "Pause/Resume"),
    ]

    filter_text = reactive("")
    paused = reactive(False)
    line_count = reactive(0)

    def __init__(self, command: List[str]):
        super().__init__()
        self.command = command
        self.interceptor = None
        self.log_lines: List[LogLine] = []

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        yield Header()
        yield Vertical(
            Input(placeholder="Filter logs...", id="filter_input"),
            RichLog(id="log_display", auto_scroll=True),
            id="main_container",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the interceptor when the app mounts."""
        self.interceptor = PTYInterceptor(
            command=self.command, on_output=self.handle_log_output
        )
        self.interceptor.start()

        # Set up filter input handler
        filter_input = self.query_one("#filter_input", Input)
        filter_input.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter input changes."""
        if event.input.id == "filter_input":
            self.filter_text = event.value
            self.update_log_display()

    def handle_log_output(self, line: str) -> None:
        """Handle new log output from the intercepted process."""
        if not self.paused:
            log_line = LogLine(line)
            self.log_lines.append(log_line)
            self.line_count = len(self.log_lines)

            # Keep only the last 10,000 lines to prevent memory issues
            if len(self.log_lines) > 10000:
                self.log_lines = self.log_lines[-10000:]

            # Update display if line matches filter
            if self.matches_filter(log_line):
                self.call_from_thread(self.add_log_line, log_line)

    def matches_filter(self, log_line: LogLine) -> bool:
        """Check if a log line matches the current filter."""
        if not self.filter_text:
            return True

        # Simple case-insensitive substring matching
        return self.filter_text.lower() in log_line.content.lower()

    def add_log_line(self, log_line: LogLine) -> None:
        """Add a log line to the display."""
        log_widget = self.query_one("#log_display", RichLog)
        # Apply Rich-based coloring instead of ANSI codes
        rich_content = apply_rich_coloring(log_line.content.rstrip('\n'))
        log_widget.write(rich_content, scroll_end=True)

    def update_log_display(self) -> None:
        """Update the log display with filtered content."""
        log_widget = self.query_one("#log_display", RichLog)
        log_widget.clear()

        # Show filtered log lines
        for log_line in self.log_lines:
            if self.matches_filter(log_line):
                # Apply Rich-based coloring instead of ANSI codes
                rich_content = apply_rich_coloring(log_line.content.rstrip('\n'))
                log_widget.write(rich_content, scroll_end=False)

        # Scroll to end
        log_widget.scroll_end()

    def action_focus_filter(self) -> None:
        """Focus the filter input."""
        self.query_one("#filter_input", Input).focus()

    def action_focus_log(self) -> None:
        """Focus the log display."""
        self.query_one("#log_display", RichLog).focus()

    def action_clear_logs(self) -> None:
        """Clear all logs."""
        self.log_lines.clear()
        self.line_count = 0
        self.query_one("#log_display", RichLog).clear()

    def action_toggle_pause(self) -> None:
        """Toggle pause/resume of log capture."""
        self.paused = not self.paused
        # Update footer to show pause status
        self.refresh()

    def action_quit(self) -> None:
        """Quit the application."""
        if self.interceptor:
            self.interceptor.stop()
        self.exit()

    def on_unmount(self) -> None:
        """Clean up when the app unmounts."""
        if self.interceptor:
            self.interceptor.stop()


def main():
    """Main entry point for the PTY interceptor."""
    if len(sys.argv) < 2:
        print("Usage: python -m sentry_tui.pty_interceptor <command> [args...]")
        print(
            "Example: python -m sentry_tui.pty_interceptor python -m sentry_tui.dummy_app"
        )
        sys.exit(1)

    command = sys.argv[1:]
    app = SentryTUIApp(command)
    app.run()


if __name__ == "__main__":
    main()

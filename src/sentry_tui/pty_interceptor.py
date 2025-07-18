#!/usr/bin/env python3
"""
PTY-based interception for capturing process output while preserving terminal behavior.
This implementation follows the approach outlined in the feasibility document.
"""

import os
import pty
import re
import select
import signal
import subprocess
import sys
import threading
import time
from enum import Enum
from typing import Callable, List, Optional

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Footer, Header, Input, Label, RichLog, Static

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


class ProcessState(Enum):
    """Process state constants for PTY interceptor."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    RESTARTING = "restarting"
    CRASHED = "crashed"


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
    """Remove ANSI background color codes while preserving foreground colors and other formatting."""
    # Pattern to match and remove background color codes while preserving other codes
    # This handles combined codes like ESC[31;42m (red foreground, green background)

    def replace_bg_codes(match):
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

    # Pattern to match any ANSI escape sequence
    pattern = re.compile(r"\x1b\[[0-9;]*m")
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


class ServiceToggleBar(Horizontal):
    """A horizontal bar containing toggle checkboxes for each service."""

    def __init__(self, services: Optional[List[str]] = None, **kwargs):
        super().__init__(**kwargs)
        self.services = list(services) if services else []
        self.enabled_services = set(self.services)  # All services enabled by default

    def compose(self) -> ComposeResult:
        """Compose the service toggle checkboxes."""
        for service in self.services:
            yield Checkbox(
                f"[b]{service}[/b]",
                value=True,  # All services enabled by default
                id=f"service_{service}",
                compact=True,
            )

    def add_service(self, service: str) -> None:
        """Add a new service to the toggle bar if it doesn't exist."""
        if service not in self.services:
            self.services.append(service)
            self.enabled_services.add(service)  # New services enabled by default

            # Add the checkbox widget only if the widget is mounted
            if self.is_mounted:
                checkbox = Checkbox(
                    f"[b]{service}[/b]",
                    value=True,
                    id=f"service_{service}",
                    compact=True,
                )
                self.mount(checkbox)

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle checkbox state changes."""
        if event.checkbox.id and event.checkbox.id.startswith("service_"):
            service_name = event.checkbox.id.replace("service_", "")
            if event.checkbox.value:
                self.enabled_services.add(service_name)
            else:
                self.enabled_services.discard(service_name)

            # Notify parent app about the change
            self.post_message(self.ServiceToggled(service_name, event.checkbox.value))

    class ServiceToggled(Message):
        """Message sent when a service is toggled."""

        def __init__(self, service: str, enabled: bool):
            self.service = service
            self.enabled = enabled
            super().__init__()

    def is_service_enabled(self, service: str) -> bool:
        """Check if a service is enabled."""
        return service in self.enabled_services


class ProcessStatusBar(Horizontal):
    """A horizontal bar showing process status and controls."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.process_state = ProcessState.STOPPED
        self.auto_restart = False
        self.restart_count = 0
        self.pid = None
        self.command = ""

    def compose(self) -> ComposeResult:
        """Compose the process status display."""
        from textual.widgets import Static

        yield Static("Process: ", id="process_label")
        yield Static("STOPPED", id="process_state_display")
        yield Static("Auto-restart: OFF", id="auto_restart_display")
        yield Static("", id="process_info_display")

    def update_status(
        self,
        state: ProcessState,
        auto_restart: bool,
        restart_count: int = 0,
        pid: Optional[int] = None,
        command: str = "",
        ports: Optional[List[int]] = None,
        process_info: Optional[dict] = None,
    ):
        """Update the process status display."""
        self.process_state = state
        self.auto_restart = auto_restart
        self.restart_count = restart_count
        self.pid = pid
        self.command = command
        self.ports = ports or []
        self.process_info = process_info or {}

        # Update state display
        state_display = self.query_one("#process_state_display")
        state_colors = {
            ProcessState.STOPPED: "dim",
            ProcessState.STARTING: "yellow",
            ProcessState.RUNNING: "green",
            ProcessState.STOPPING: "yellow",
            ProcessState.RESTARTING: "blue",
            ProcessState.CRASHED: "red",
        }
        state_display.update(
            f"[{state_colors.get(state, 'white')}]{state.value.upper()}[/]"
        )

        # Update auto-restart display
        auto_restart_display = self.query_one("#auto_restart_display")
        auto_restart_text = "ON" if auto_restart else "OFF"
        auto_restart_color = "green" if auto_restart else "dim"
        auto_restart_display.update(
            f"Auto-restart: [{auto_restart_color}]{auto_restart_text}[/]"
        )

        # Update process info display
        process_info_display = self.query_one("#process_info_display")
        info_parts = []
        
        if pid:
            info_parts.append(f"PID: {pid}")
        
        if self.ports:
            ports_str = ",".join(map(str, self.ports))
            info_parts.append(f"Ports: {ports_str}")
        
        if self.process_info.get('memory_mb'):
            info_parts.append(f"Memory: {self.process_info['memory_mb']}MB")
            
        if self.process_info.get('cpu_percent') is not None:
            info_parts.append(f"CPU: {self.process_info['cpu_percent']}%")
            
        if restart_count > 0:
            info_parts.append(f"Restarts: {restart_count}")
            
        if command:
            # Truncate command if too long to preserve space for other info
            display_command = command if len(command) <= 40 else command[:37] + "..."
            info_parts.append(f"Command: {display_command}")

        process_info_display.update(" | ".join(info_parts))


class CommandEditScreen(ModalScreen):
    """Modal screen for editing the command."""

    CSS = """
    CommandEditScreen {
        align: center middle;
    }
    
    #edit_dialog {
        width: 80%;
        height: auto;
        border: thick $primary 80%;
        padding: 1;
        background: $surface;
    }
    
    #edit_title {
        text-align: center;
        margin-bottom: 1;
        text-style: bold;
    }
    
    #previous_command_label {
        text-style: dim;
        margin-bottom: 1;
    }
    
    #command_input {
        margin-bottom: 1;
    }
    
    #edit_buttons {
        align: center middle;
        height: auto;
    }
    
    #edit_buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, current_command: str, previous_command: str = "", **kwargs):
        super().__init__(**kwargs)
        self.current_command = current_command
        self.previous_command = previous_command

    def compose(self) -> ComposeResult:
        """Compose the command edit dialog."""
        with Container(id="edit_dialog"):
            yield Label("Edit Command", id="edit_title")
            
            if self.previous_command:
                yield Label(f"Previous: {self.previous_command}", id="previous_command_label")
                
            yield Input(
                value=self.current_command,
                placeholder="Enter command to run (e.g., getsentry devserver --workers)",
                id="command_input"
            )
            
            with Horizontal(id="edit_buttons"):
                yield Button("Save", variant="primary", id="save_button")
                yield Button("Cancel", variant="default", id="cancel_button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "save_button":
            command_input = self.query_one("#command_input", Input)
            new_command = command_input.value.strip()
            if new_command:
                self.dismiss(new_command)
            else:
                # Don't allow empty commands
                pass
        elif event.button.id == "cancel_button":
            self.dismiss(None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in the input field."""
        if event.input.id == "command_input":
            new_command = event.input.value.strip()
            if new_command:
                self.dismiss(new_command)


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
        """Extract service name from Sentry Honcho format.

        Format: HH:MM:SS service_name | log_message

        Examples:
        - "06:40:47 system  | webpack started (pid=83946)"
        - "06:40:48 server  | Using configuration 'getsentry.conf.settings.dev'"
        - "06:40:51 webpack | <i> [webpack-dev-server] [HPM] Proxy created..."

        Source Code References:
        - Honcho process manager: /Users/me/aaa/sentry/sentry/src/sentry/runner/commands/devserver.py:507-509
        - SentryPrinter format logic: /Users/me/aaa/sentry/sentry/src/sentry/runner/formatting.py:78-120
        - Service names from daemons: /Users/me/aaa/sentry/sentry/src/sentry/runner/commands/devserver.py:21-27
        - Color scheme: /Users/me/aaa/sentry/sentry/src/sentry/runner/formatting.py:18-24
        """
        # Remove ANSI color codes first
        clean_content = strip_ansi_codes(self.content)

        # Look for pattern: HH:MM:SS service_name |
        match = re.match(r"^\d{2}:\d{2}:\d{2}\s+([a-zA-Z0-9._-]+)\s*\|", clean_content)
        if match:
            return match.group(1).strip()

        # Fallback: try to find service name in known services
        for service in SENTRY_SERVICE_COLORS.keys():
            if service in clean_content:
                return service

        return "unknown"

    def _extract_level(self) -> str:
        """Extract log level from Sentry Honcho format: HH:MM:SS service_name | log_message

        Since Honcho format doesn't include explicit log levels, we infer from content.

        Source Code References:
        - Honcho doesn't add log levels: /Users/me/aaa/sentry/sentry/src/sentry/runner/formatting.py:110-118
        - Original services just output raw logs to Honcho
        - Log level inference based on common error patterns
        """
        # Remove ANSI color codes first
        clean_content = strip_ansi_codes(self.content)

        # Look for common error indicators
        content_lower = clean_content.lower()
        if any(
            word in content_lower
            for word in ["error", "exception", "traceback", "failed", "critical"]
        ):
            return "ERROR"
        elif any(word in content_lower for word in ["warning", "warn", "deprecated"]):
            return "WARNING"
        elif any(word in content_lower for word in ["debug"]):
            return "DEBUG"

        return "INFO"  # Default level

    def _extract_module_name(self) -> str:
        """Extract module name from Sentry Honcho format: HH:MM:SS service_name | log_message

        Since Honcho format doesn't include explicit module names, we use the service name.

        Source Code References:
        - Service names are process names: /Users/me/aaa/sentry/sentry/src/sentry/runner/commands/devserver.py:21-27
        - Honcho manages these as separate processes: /Users/me/aaa/sentry/sentry/src/sentry/runner/commands/devserver.py:511-517
        - No module-level granularity in this format
        """
        # Use service name as module name since no explicit module in this format
        return self.service

    def _extract_message(self) -> str:
        """Extract the actual log message from Sentry Honcho format: HH:MM:SS service_name | log_message

        Source Code References:
        - Raw message output: /Users/me/aaa/sentry/sentry/src/sentry/runner/formatting.py:116-118
        - Honcho adds timestamp and service prefix: honcho.printer.Printer (external library)
        - SentryPrinter adds ANSI colors but preserves message content
        """
        # Remove ANSI color codes first
        clean_content = strip_ansi_codes(self.content)

        # Look for message after the pipe separator
        match = re.search(
            r"^\d{2}:\d{2}:\d{2}\s+[a-zA-Z0-9._-]+\s*\|\s*(.*)$", clean_content
        )
        if match:
            return match.group(1).strip()

        # Fallback: return the entire clean content
        return clean_content.strip()


class PTYInterceptor:
    """PTY-based process interceptor that captures output while preserving terminal behavior."""

    def __init__(
        self,
        command: List[str],
        on_output: Optional[Callable[[str], None]] = None,
        auto_restart: bool = False,
    ):
        self.command = command
        self.on_output = on_output or self._default_output_handler
        self.process = None
        self.master_fd = None
        self.slave_fd = None
        self.running = False
        self.output_thread = None
        self.monitor_thread = None
        self.buffer = ""
        self.state = ProcessState.STOPPED
        self.auto_restart = auto_restart
        self.restart_count = 0
        self.max_restart_attempts = 5
        self.restart_delay = 1.0  # seconds
        self.state_callbacks = []  # List of callbacks to notify on state changes
        self._state_lock = threading.Lock()  # Lock for thread-safe state management
        self._stop_event = threading.Event()  # Event to signal manual stop operations
        self.detected_ports = set()  # Track detected ports from logs
        self.process_info = {}  # Additional process information
        self.last_known_ports = set()  # Preserve ports from previous process during restart
        self._process_ready_event = threading.Event()  # Signal when process is ready for port detection

    def _default_output_handler(self, line: str):
        """Default output handler that prints to stdout."""
        print(line, end="")

    def _detect_ports_from_process(self):
        """Detect ports opened by the current process using system tools."""
        if not self.process:
            return
            
        try:
            pid = self.process.pid
            ports = set()
            
            # Try different methods to get port information
            try:
                # Method 1: Use psutil if available (most reliable)
                import psutil
                proc = psutil.Process(pid)
                connections = proc.connections(kind='inet')
                for conn in connections:
                    if conn.status == psutil.CONN_LISTEN and conn.laddr:
                        ports.add(conn.laddr.port)
                        
            except ImportError:
                # Method 2: Use netstat as fallback
                try:
                    import subprocess
                    # Use netstat to find listening ports for this PID
                    result = subprocess.run(
                        ['netstat', '-tulpn'], 
                        capture_output=True, 
                        text=True, 
                        timeout=2
                    )
                    
                    for line in result.stdout.split('\n'):
                        if f'{pid}/' in line and 'LISTEN' in line:
                            # Parse netstat output: tcp 0 0 127.0.0.1:8000 0.0.0.0:* LISTEN 12345/python
                            parts = line.split()
                            if len(parts) >= 4:
                                addr = parts[3]  # 127.0.0.1:8000
                                if ':' in addr:
                                    port_str = addr.split(':')[-1]
                                    try:
                                        port = int(port_str)
                                        if 1000 <= port <= 65535:
                                            ports.add(port)
                                    except ValueError:
                                        pass
                                        
                except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                    # Method 3: Use lsof as another fallback (macOS/Linux)
                    try:
                        result = subprocess.run(
                            ['lsof', '-Pan', '-p', str(pid), '-i'], 
                            capture_output=True, 
                            text=True, 
                            timeout=2
                        )
                        
                        for line in result.stdout.split('\n'):
                            if 'LISTEN' in line:
                                # Parse lsof output: python 12345 user 5u IPv4 TCP *:8000 (LISTEN)
                                parts = line.split()
                                for part in parts:
                                    if ':' in part and part.endswith('(LISTEN)'):
                                        port_str = part.split(':')[-1].replace('(LISTEN)', '')
                                        try:
                                            port = int(port_str)
                                            if 1000 <= port <= 65535:
                                                ports.add(port)
                                        except ValueError:
                                            pass
                                            
                    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, FileNotFoundError):
                        pass
            
            # Update detected ports
            if ports:  # Only update if we actually found ports
                self.detected_ports = ports
                self.last_known_ports = ports.copy()  # Preserve for restart scenarios
            elif not self.detected_ports and self.last_known_ports:
                # If no ports detected but we have previous knowledge, keep the old ports temporarily
                # This helps during restart cycles where the process might not be fully ready
                self.detected_ports = self.last_known_ports.copy()
            
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            # Process doesn't exist or no permission
            self.detected_ports.clear()

    def _wait_for_process_ready_and_update_info(self):
        """Wait for process to be ready and then update process information."""
        if not self.process:
            return
            
        # Wait for process ready signal with timeout
        if self._process_ready_event.wait(timeout=5.0):
            # Process is ready, proceed with port detection
            self._detect_ports_from_process()
        else:
            # Timeout - try anyway but preserve previous port info if available
            if self.last_known_ports and not self.detected_ports:
                self.detected_ports = self.last_known_ports.copy()
            self._detect_ports_from_process()
            
        self._update_basic_process_info()

    def _update_process_info(self):
        """Update additional process information if available."""
        if not self.process:
            return
            
        # For regular updates (not startup), just update immediately
        self._detect_ports_from_process()
        self._update_basic_process_info()
            
    def _update_basic_process_info(self):
        """Update basic process information like memory and CPU."""
        if not self.process:
            return
            
        try:
            # Try to get process info using psutil if available
            import psutil
            
            proc = psutil.Process(self.process.pid)
            
            # Get memory info immediately (this is fast and doesn't block)
            memory_info = proc.memory_info()
            
            # Get CPU percent with non-blocking call (interval=None means non-blocking)
            # First call returns 0.0, subsequent calls return meaningful values
            cpu_percent = proc.cpu_percent(interval=None)
            
            self.process_info = {
                'memory_mb': round(memory_info.rss / 1024 / 1024, 1),
                'cpu_percent': round(cpu_percent, 1) if cpu_percent > 0 else None,  # Don't show 0% initially
                'status': proc.status(),
                'create_time': proc.create_time(),
            }
        except ImportError:
            # psutil not available, use basic info
            self.process_info = {
                'status': 'running' if self.process.poll() is None else 'terminated'
            }
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process doesn't exist or no permission
            self.process_info = {}

    def _check_process_ready_indicators(self, line: str):
        """Check if log line indicates the process is ready for port detection."""
        if self._process_ready_event.is_set():
            return  # Already signaled
            
        clean_line = strip_ansi_codes(line).lower()
        
        # Common patterns that indicate a server/process is ready
        ready_patterns = [
            'running on',           # "Running on http://127.0.0.1:8000"
            'listening on',         # "Listening on port 8000"
            'server started',       # "Server started on port 8000"
            'development server',   # Django "Development server is running"
            'starting development', # "Starting development server"
            'webpack compiled',     # Webpack ready
            'compiled successfully', # Build completed
            'ready in',            # Various "Ready in XXXms" messages
            'listening at',        # "Listening at http://..."
            'bound to',            # Process bound to address
            'started server',      # "Started server on"
            'devserver.*ready',    # Sentry specific
        ]
        
        for pattern in ready_patterns:
            if re.search(pattern, clean_line):
                # Signal that the process appears ready
                self._process_ready_event.set()
                # Start a thread to update process info now that it's ready
                threading.Thread(
                    target=self._wait_for_process_ready_and_update_info,
                    daemon=True
                ).start()
                # Trigger status callbacks to update UI immediately
                self._notify_status_change()
                break

    def _notify_status_change(self):
        """Notify all callbacks that status may have changed."""
        callbacks = []
        with self._state_lock:
            callbacks = self.state_callbacks.copy()
        
        # Notify callbacks outside the lock to prevent deadlocks
        for callback in callbacks:
            try:
                callback(self.state)
            except Exception:
                # Ignore callback errors to prevent affecting other callbacks
                pass

    def add_state_callback(self, callback: Callable[[ProcessState], None]):
        """Add a callback to be notified when process state changes (thread-safe)."""
        with self._state_lock:
            self.state_callbacks.append(callback)

    def remove_state_callback(self, callback: Callable[[ProcessState], None]):
        """Remove a state change callback (thread-safe)."""
        with self._state_lock:
            if callback in self.state_callbacks:
                self.state_callbacks.remove(callback)

    def _set_state(self, new_state: ProcessState):
        """Set the process state and notify callbacks (thread-safe)."""
        callbacks = []
        with self._state_lock:
            if self.state != new_state:
                self.state = new_state
                # Notify callbacks outside the lock to prevent deadlocks
                callbacks = self.state_callbacks.copy()

        # Call callbacks outside the lock (only if state changed)
        for callback in callbacks:
            try:
                callback(new_state)
            except Exception:
                # Ignore callback errors to prevent cascading failures
                pass

    def start(self):
        """Start the PTY-based interception."""
        with self._state_lock:
            if self.state == ProcessState.RUNNING:
                return  # Already running

        self._set_state(ProcessState.STARTING)

        # Clear the stop event for new start
        self._stop_event.clear()
        
        # Clear the process ready event for new start
        self._process_ready_event.clear()

        try:
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

            # Start process monitoring thread
            self.monitor_thread = threading.Thread(
                target=self._monitor_process, daemon=True
            )
            self.monitor_thread.start()

            self._set_state(ProcessState.RUNNING)
        except Exception:
            self._set_state(ProcessState.CRASHED)
            raise

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
            # Check if this line indicates the process is ready
            self._check_process_ready_indicators(line)
            self.on_output(line + "\n")

    def _monitor_process(self):
        """Monitor the process and handle auto-restart if enabled."""
        while self.running and self.process:
            try:
                # Check if process is still running
                exit_code = self.process.poll()
                if exit_code is not None:
                    # Process has terminated
                    self.running = False

                    # Use thread-safe state management
                    with self._state_lock:
                        is_manual_stop = self._stop_event.is_set()
                        current_state = self.state

                    # Only set state if this is not a manual stop operation
                    if not is_manual_stop and current_state != ProcessState.STOPPING:
                        if exit_code == 0:
                            self._set_state(ProcessState.STOPPED)
                        else:
                            self._set_state(ProcessState.CRASHED)

                    # Handle auto-restart only if not manually stopping and auto-restart enabled
                    with self._state_lock:
                        should_restart = (
                            self.auto_restart
                            and not is_manual_stop
                            and self.state
                            not in [ProcessState.STOPPING, ProcessState.STOPPED]
                            and self.restart_count < self.max_restart_attempts
                        )

                    if should_restart:
                        self.restart_count += 1
                        self._set_state(ProcessState.RESTARTING)
                        time.sleep(self.restart_delay)
                        try:
                            # Reset state to stopped before restarting
                            with self._state_lock:
                                self.state = ProcessState.STOPPED
                            self.start()
                        except Exception:
                            # Restart failed
                            self._set_state(ProcessState.CRASHED)
                    elif self.restart_count >= self.max_restart_attempts:
                        # Max restart attempts reached
                        self._set_state(ProcessState.CRASHED)

                    break

                time.sleep(0.1)  # Check every 100ms
            except Exception:
                # Error monitoring process
                break

    def stop(self, force: bool = False):
        """Stop the PTY interception.

        Args:
            force: If True, use SIGKILL immediately instead of SIGTERM.
        """
        with self._state_lock:
            if self.state == ProcessState.STOPPED:
                return  # Already stopped

            # Signal that this is a manual stop operation
            self._stop_event.set()

        self._set_state(ProcessState.STOPPING)
        self.running = False

        if self.process:
            try:
                # Send appropriate signal to process group
                sig = signal.SIGKILL if force else signal.SIGTERM
                os.killpg(os.getpgid(self.process.pid), sig)

                # Wait for process to terminate
                timeout = 1 if force else 5
                self.process.wait(timeout=timeout)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                # Force kill if necessary (only if not already using SIGKILL)
                if not force:
                    try:
                        os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass

        # Clean up file descriptors
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except OSError:
                # File descriptor was already closed
                pass
            finally:
                self.master_fd = None

        # Clean up threads
        if self.output_thread and self.output_thread.is_alive():
            self.output_thread.join(timeout=1)

        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1)

        # Clean up process reference
        self.process = None

        # Clear process information when stopping (memory, CPU, etc.)
        self.process_info.clear()
        self.detected_ports.clear()
        # Note: Keep last_known_ports for restart scenarios
        self._process_ready_event.clear()

        # Set final state
        self._set_state(ProcessState.STOPPED)

    def graceful_shutdown(self):
        """Gracefully shutdown the process using SIGTERM."""
        self.auto_restart = False  # Disable auto-restart for graceful shutdown
        self.stop(force=False)

    def force_quit(self):
        """Force quit the process using SIGKILL."""
        self.auto_restart = False  # Disable auto-restart for force quit
        self.stop(force=True)

    def restart(self, force: bool = False):
        """Restart the process.

        Args:
            force: If True, use SIGKILL to stop the process before restarting.
        """
        with self._state_lock:
            if self.state == ProcessState.RUNNING:
                # Don't use the stop event for restart - we want to restart
                pass

        if self.state == ProcessState.RUNNING:
            # Preserve port information during restart
            preserved_ports = self.detected_ports.copy()
            self.stop(force=force)
            # Restore preserved ports for restart scenario
            self.last_known_ports = preserved_ports
            # Wait for process to stop with timeout
            timeout = 0
            while (
                self.state not in [ProcessState.STOPPED, ProcessState.CRASHED]
                and timeout < 50
            ):
                time.sleep(0.1)
                timeout += 1

        # Reset restart counter and ensure clean state
        with self._state_lock:
            self.restart_count = 0
            self.state = ProcessState.STOPPED

        self.start()

    def toggle_auto_restart(self):
        """Toggle auto-restart functionality."""
        self.auto_restart = not self.auto_restart
        return self.auto_restart

    def get_status(self):
        """Get current process status information (thread-safe)."""
        with self._state_lock:
            # Update process info if we have a running process
            if self.process and self.state == ProcessState.RUNNING:
                # Always update basic process info (memory is fast and doesn't need to wait)
                self._update_basic_process_info()
                
                # Handle port detection based on readiness
                if not self._process_ready_event.is_set():
                    # Use preserved port info if available, otherwise try immediate detection
                    if self.last_known_ports and not self.detected_ports:
                        self.detected_ports = self.last_known_ports.copy()
                    else:
                        # Try immediate port detection (may be empty initially)
                        self._detect_ports_from_process()
                else:
                    # Process is ready, update ports normally
                    self._detect_ports_from_process()
            
            return {
                "state": self.state,
                "auto_restart": self.auto_restart,
                "restart_count": self.restart_count,
                "max_restart_attempts": self.max_restart_attempts,
                "pid": self.process.pid if self.process else None,
                "command": " ".join(self.command),
                "ports": sorted(list(self.detected_ports)),
                "process_info": self.process_info.copy(),
            }


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
    
    #service_toggle_bar {
        height: auto;
        margin: 0;
        padding: 0;
    }
    
    #service_toggle_bar Checkbox {
        margin: 0 1;
        padding: 0;
        width: auto;
    }
    
    #process_status_bar {
        height: 1;
        background: $surface;
        color: $text;
        padding: 0 1;
        margin: 0;
    }
    
    #process_status_bar Static {
        margin: 0 1;
        padding: 0;
        width: auto;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+c", "quit", "Quit"),
        Binding("f", "focus_filter", "Focus Filter"),
        Binding("l", "focus_log", "Focus Log"),
        Binding("c", "clear_logs", "Clear Logs"),
        Binding("p", "toggle_pause", "Pause/Resume"),
        Binding("s", "graceful_shutdown", "Graceful Shutdown"),
        Binding("k", "force_quit", "Force Quit"),
        Binding("r", "restart", "Restart"),
        Binding("shift+r", "force_restart", "Force Restart"),
        Binding("a", "toggle_auto_restart", "Toggle Auto-restart"),
        Binding("e", "edit_command", "Edit Command"),
    ]

    filter_text = reactive("")
    paused = reactive(False)
    line_count = reactive(0)
    current_command = reactive("")
    previous_command = reactive("")
    process_state = reactive(ProcessState.STOPPED)
    auto_restart_enabled = reactive(False)

    def __init__(self, command: List[str], auto_restart: bool = False):
        super().__init__()
        self.command = command
        self.current_command = " ".join(command)  # Initialize reactive variable
        self.previous_command = ""  # No previous command initially
        self.interceptor = None
        self.log_lines: List[LogLine] = []
        self.discovered_services: set = set()
        self.auto_restart = auto_restart
        self.auto_restart_enabled = auto_restart

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        yield Header()
        yield Vertical(
            Input(placeholder="Filter logs...", id="filter_input"),
            ServiceToggleBar(services=[], id="service_toggle_bar"),
            ProcessStatusBar(id="process_status_bar"),
            RichLog(id="log_display", auto_scroll=True),
            id="main_container",
        )
        yield Footer()

    def on_mount(self) -> None:
        """Initialize the interceptor when the app mounts."""
        self.interceptor = PTYInterceptor(
            command=self.command,
            on_output=self.handle_log_output,
            auto_restart=self.auto_restart,
        )

        # Set up process state callback
        self.interceptor.add_state_callback(self.on_process_state_changed)

        # Start the interceptor
        self.interceptor.start()

        # Set up filter input handler
        filter_input = self.query_one("#filter_input", Input)
        filter_input.focus()

        # Update initial process status
        self.update_process_status()

    def on_process_state_changed(self, new_state: ProcessState) -> None:
        """Handle process state changes."""
        self.process_state = new_state
        # Use a small delay to ensure state is fully updated
        self.call_from_thread(self.update_process_status)

    def update_process_status(self) -> None:
        """Update the process status display."""
        if self.interceptor:
            status = self.interceptor.get_status()
            process_status_bar = self.query_one("#process_status_bar", ProcessStatusBar)
            process_status_bar.update_status(
                state=status["state"],
                auto_restart=status["auto_restart"],
                restart_count=status["restart_count"],
                pid=status["pid"],
                command=status["command"],
                ports=status.get("ports", []),
                process_info=status.get("process_info", {}),
            )
            self.auto_restart_enabled = status["auto_restart"]
            # Force a refresh of the display
            self.refresh()

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter input changes."""
        if event.input.id == "filter_input":
            self.filter_text = event.value
            self.update_log_display()

    def on_service_toggle_bar_service_toggled(
        self, event: ServiceToggleBar.ServiceToggled
    ) -> None:
        """Handle service toggle events."""
        # Update the log display when service toggles change
        self.update_log_display()

    def handle_log_output(self, line: str) -> None:
        """Handle new log output from the intercepted process."""
        if not self.paused:
            log_line = LogLine(line)
            self.log_lines.append(log_line)
            self.line_count = len(self.log_lines)

            # Discover new services dynamically
            if log_line.service not in self.discovered_services:
                self.discovered_services.add(log_line.service)
                self.call_from_thread(self.add_service_to_toggle_bar, log_line.service)

            # Keep only the last 10,000 lines to prevent memory issues
            if len(self.log_lines) > 10000:
                self.log_lines = self.log_lines[-10000:]

            # Update display if line matches filter
            if self.matches_filter(log_line):
                self.call_from_thread(self.add_log_line, log_line)

    def matches_filter(self, log_line: LogLine) -> bool:
        """Check if a log line matches the current filter."""
        # Check if service is enabled in toggle bar (only if app is running)
        try:
            service_toggle_bar = self.query_one("#service_toggle_bar", ServiceToggleBar)

            # If no services have been discovered yet, allow all services
            if not service_toggle_bar.services:
                pass  # Skip service filtering when no services are available
            elif not service_toggle_bar.is_service_enabled(log_line.service):
                return False
        except Exception:
            # If service toggle bar is not available (e.g., in tests), skip service filtering
            pass

        # Check text filter
        if not self.filter_text:
            return True

        # Simple case-insensitive substring matching
        return self.filter_text.lower() in log_line.content.lower()

    def add_service_to_toggle_bar(self, service: str) -> None:
        """Add a new service to the toggle bar."""
        service_toggle_bar = self.query_one("#service_toggle_bar", ServiceToggleBar)
        service_toggle_bar.add_service(service)

    def add_log_line(self, log_line: LogLine) -> None:
        """Add a log line to the display."""
        log_widget = self.query_one("#log_display", RichLog)
        # Apply Rich-based coloring instead of ANSI codes
        rich_content = apply_rich_coloring(log_line.content.rstrip("\n"))
        log_widget.write(rich_content, scroll_end=True)

    def update_log_display(self) -> None:
        """Update the log display with filtered content."""
        log_widget = self.query_one("#log_display", RichLog)
        log_widget.clear()

        # Show filtered log lines
        for log_line in self.log_lines:
            if self.matches_filter(log_line):
                # Apply Rich-based coloring instead of ANSI codes
                rich_content = apply_rich_coloring(log_line.content.rstrip("\n"))
                log_widget.write(rich_content, scroll_end=False)

        # Scroll to end
        log_widget.scroll_end()

    def action_graceful_shutdown(self) -> None:
        """Gracefully shutdown the devserver."""
        if self.interceptor:
            self.interceptor.graceful_shutdown()
            # Force an immediate status update
            self.update_process_status()

    def action_force_quit(self) -> None:
        """Force quit the devserver."""
        if self.interceptor:
            self.interceptor.force_quit()
            # Force an immediate status update
            self.update_process_status()

    def action_restart(self) -> None:
        """Restart the devserver gracefully."""
        if self.interceptor:
            self.interceptor.restart(force=False)
            # Force an immediate status update
            self.update_process_status()

    def action_force_restart(self) -> None:
        """Force restart the devserver."""
        if self.interceptor:
            self.interceptor.restart(force=True)
            # Force an immediate status update
            self.update_process_status()

    def action_toggle_auto_restart(self) -> None:
        """Toggle auto-restart functionality."""
        if self.interceptor:
            self.interceptor.toggle_auto_restart()
            # Force an immediate status update
            self.update_process_status()

    async def action_edit_command(self) -> None:
        """Edit the command to be run."""
        def update_command(new_command: str) -> None:
            if new_command is not None:
                # Store previous command
                self.previous_command = self.current_command
                # Parse new command into list
                new_command_list = new_command.split()
                self.command = new_command_list
                self.current_command = new_command
                # Update the interceptor if it exists
                if self.interceptor:
                    self.interceptor.command = new_command_list
                # Update status display
                self.update_process_status()

        # Show the edit dialog
        result = await self.push_screen(
            CommandEditScreen(self.current_command, self.previous_command),
            update_command
        )

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

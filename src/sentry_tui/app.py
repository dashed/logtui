"""Main SentryTUI application."""

import time
from typing import List

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Input, RichLog

from .constants import ProcessState
from .log_processing import LogLine
from .pty_core import PTYInterceptor
from .ui_components import CommandEditScreen, EnhancedStatusBar, ProcessStatusBar, ServiceToggleBar
from .utils import apply_rich_coloring


class FilterInput(Input):
    """Custom Input widget that allows certain keys to pass through to app bindings."""
    
    def check_consume_key(self, key: str, character: str | None) -> bool:
        """Check if the widget may consume the given key.
        
        Allow 'l' and 'f' keys to pass through to app bindings for focus switching.
        
        Args:
            key: A key identifier.
            character: A character associated with the key, or `None` if there isn't one.
            
        Returns:
            `True` if the widget may capture the key, or `False` if it should pass through.
        """
        # Allow 'l' and 'f' keys to pass through to app bindings
        if key in ("l", "f"):
            return False
            
        # For all other keys, use the default Input behavior
        return character is not None and character.isprintable()


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
    
    #service_toggle_bar Button {
        margin: 0 1;
        padding: 0;
        width: auto;
        height: 1;
        min-width: 10;
        max-width: 10;
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
    
    #enhanced_status_bar {
        height: 1;
        background: $surface;
        color: $text;
        padding: 0 1;
        border-top: solid $primary;
        dock: bottom;
    }
    
    #enhanced_status_bar Static {
        margin: 0 1;
        padding: 0;
        width: auto;
    }
    
    #enhanced_status_bar .spacer {
        width: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("ctrl+c", "quit", "Quit", priority=True),
        Binding("f", "focus_filter", "Focus Filter", priority=True),
        Binding("l", "focus_log", "Focus Log", priority=True),
        Binding("c", "clear_logs", "Clear Logs", priority=True),
        Binding("p", "toggle_pause", "Pause/Resume", priority=True),
        Binding("s", "graceful_shutdown", "Graceful Shutdown", priority=True),
        Binding("k", "force_quit", "Force Quit", priority=True),
        Binding("r", "restart", "Restart", priority=True),
        Binding("shift+r", "force_restart", "Force Restart", priority=True),
        Binding("a", "toggle_auto_restart", "Toggle Auto-restart", priority=True),
        Binding("e", "edit_command", "Edit Command", priority=True),
    ]

    filter_text = reactive("")
    paused = reactive(False)
    line_count = reactive(0)
    filtered_line_count = reactive(0)
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
        
        # Performance tracking
        self.last_log_time = time.time()
        self.log_timestamps = []
        self.update_enhanced_status_timer = None

    def compose(self) -> ComposeResult:
        """Compose the TUI layout."""
        yield Header()
        yield Vertical(
            FilterInput(placeholder="Filter logs...", id="filter_input"),
            ServiceToggleBar(services=[], id="service_toggle_bar"),
            ProcessStatusBar(id="process_status_bar"),
            RichLog(id="log_display", auto_scroll=True),
            EnhancedStatusBar(id="enhanced_status_bar"),
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
        filter_input = self.query_one("#filter_input", FilterInput)
        filter_input.focus()

        # Update initial process status
        self.update_process_status()
        
        # Update initial enhanced status bar
        self.update_enhanced_status_bar()
        
        # Set up periodic enhanced status bar updates
        self.update_enhanced_status_timer = self.set_interval(1.0, self.update_enhanced_status_bar)

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

    def update_enhanced_status_bar(self) -> None:
        """Update the enhanced status bar with current metrics."""
        try:
            enhanced_status_bar = self.query_one("#enhanced_status_bar", EnhancedStatusBar)
            
            # Calculate filtered line count
            filtered_count = 0
            for log_line in self.log_lines:
                if self.matches_filter(log_line):
                    filtered_count += 1
            self.filtered_line_count = filtered_count
            
            # Calculate logs per second (using last 10 seconds)
            current_time = time.time()
            # Remove timestamps older than 10 seconds
            self.log_timestamps = [ts for ts in self.log_timestamps if current_time - ts <= 10]
            logs_per_sec = len(self.log_timestamps) / min(10, max(1, current_time - self.last_log_time))
            
            # Get basic memory usage estimate (number of lines * rough estimate per line)
            memory_usage = len(self.log_lines) * 0.001  # Rough estimate: 1KB per line
            
            enhanced_status_bar.update_status(
                total_lines=self.line_count,
                filtered_lines=self.filtered_line_count,
                active_filter=self.filter_text,
                service_count=len(self.discovered_services),
                logs_per_sec=logs_per_sec,
                memory_usage=int(memory_usage),
            )
        except Exception:
            # If enhanced status bar is not available, skip silently
            pass

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter input changes."""
        if event.input.id == "filter_input":
            self.filter_text = event.value
            self.update_log_display()
            # Update enhanced status bar when filter changes
            self.update_enhanced_status_bar()

    def on_service_toggle_bar_service_toggled(
        self, event: ServiceToggleBar.ServiceToggled
    ) -> None:
        """Handle service toggle events."""
        # Update the log display when service toggles change
        self.update_log_display()
        # Update enhanced status bar when service toggles change
        self.update_enhanced_status_bar()

    def handle_log_output(self, line: str) -> None:
        """Handle new log output from the intercepted process."""
        if not self.paused:
            log_line = LogLine(line)
            self.log_lines.append(log_line)
            self.line_count = len(self.log_lines)
            
            # Track timestamp for performance metrics
            current_time = time.time()
            self.log_timestamps.append(current_time)
            self.last_log_time = current_time

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

    def action_quit(self) -> None:
        """Quit the application."""
        if self.interceptor:
            self.interceptor.stop()
        self.exit()

    def action_focus_filter(self) -> None:
        """Focus the filter input."""
        self.query_one("#filter_input", FilterInput).focus()

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
        await self.push_screen(
            CommandEditScreen(self.current_command, self.previous_command),
            update_command,
        )

    def on_unmount(self) -> None:
        """Clean up when the app unmounts."""
        if self.interceptor:
            self.interceptor.stop()
        
        # Clean up the enhanced status bar timer
        if self.update_enhanced_status_timer:
            self.update_enhanced_status_timer.stop()

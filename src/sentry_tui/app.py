"""Main SentryTUI application."""

from typing import List

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Input, RichLog

from .constants import ProcessState
from .log_processing import LogLine
from .pty_core import PTYInterceptor
from .ui_components import CommandEditScreen, ProcessStatusBar, ServiceToggleBar
from .utils import apply_rich_coloring


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
        """Handle service toggle changes."""
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
        log_display = self.query_one("#log_display", RichLog)
        # Apply Rich-based coloring instead of ANSI codes
        colored_text = apply_rich_coloring(log_line.content.rstrip("\n"))
        log_display.write(colored_text, scroll_end=True)

    def update_log_display(self) -> None:
        """Update the log display based on current filters."""
        log_display = self.query_one("#log_display", RichLog)
        log_display.clear()

        # Re-display all matching lines
        for log_line in self.log_lines:
            if self.matches_filter(log_line):
                colored_text = apply_rich_coloring(log_line.content.rstrip("\n"))
                log_display.write(colored_text, scroll_end=False)

        # Scroll to end after all lines are added
        log_display.scroll_end()

    def action_quit(self) -> None:
        """Quit the application."""
        if self.interceptor:
            self.interceptor.stop()
        self.exit()

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

    def action_graceful_shutdown(self) -> None:
        """Gracefully shutdown the devserver."""
        if self.interceptor:
            self.interceptor.graceful_shutdown()

    def action_force_quit(self) -> None:
        """Force quit the devserver."""
        if self.interceptor:
            self.interceptor.force_quit()

    def action_restart(self) -> None:
        """Restart the devserver (graceful)."""
        if self.interceptor:
            self.interceptor.restart(force=False)

    def action_force_restart(self) -> None:
        """Force restart the devserver."""
        if self.interceptor:
            self.interceptor.restart(force=True)

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

    def on_unmount(self) -> None:
        """Clean up when the app unmounts."""
        if self.interceptor:
            self.interceptor.stop()
"""UI components for sentry-tui."""

from typing import List, Optional

from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.message import Message
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, Static

from .constants import ProcessState


class ServiceToggleBar(Horizontal):
    """Horizontal bar with service toggle checkboxes."""

    class ServiceToggled(Message):
        """Message sent when a service is toggled."""

        def __init__(self, service: str, enabled: bool):
            self.service = service
            self.enabled = enabled
            super().__init__()

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

    def is_service_enabled(self, service: str) -> bool:
        """Check if a service is currently enabled."""
        return service in self.enabled_services


class ProcessStatusBar(Horizontal):
    """Status bar showing process information."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.process_state = ProcessState.STOPPED
        self.auto_restart = False
        self.restart_count = 0
        self.pid = None
        self.command = ""
        self.ports = []
        self.process_info = {}

    def compose(self) -> ComposeResult:
        """Compose the status bar."""
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

        if self.process_info.get("memory_mb"):
            info_parts.append(f"Memory: {self.process_info['memory_mb']}MB")

        if self.process_info.get("cpu_percent") is not None:
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
                yield Label(
                    f"Previous: {self.previous_command}", id="previous_command_label"
                )

            yield Input(
                value=self.current_command,
                placeholder="Enter command to run (e.g., getsentry devserver --workers)",
                id="command_input",
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

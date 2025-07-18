"""Core PTY functionality for process interception."""

import fcntl
import os
import pty
import select
import signal
import subprocess
import threading
import time
from typing import Callable, List, Optional

from .constants import ProcessState
from .process_monitor import ProcessMonitor


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
        self._stop_event = threading.Event()  # Event to signal manual stop operations
        
        # Initialize process monitor
        self.monitor = ProcessMonitor()
        
        # Expose state_callbacks for backward compatibility
        self.state_callbacks = self.monitor.state_callbacks
        
    def _default_output_handler(self, line: str):
        """Default output handler that prints to stdout."""
        print(line, end="")

    def add_state_callback(self, callback: Callable[[ProcessState], None]):
        """Add a callback to be notified when process state changes (thread-safe)."""
        self.monitor.add_state_callback(callback)

    def remove_state_callback(self, callback: Callable[[ProcessState], None]):
        """Remove a state change callback (thread-safe)."""
        self.monitor.remove_state_callback(callback)

    def _set_state(self, new_state: ProcessState):
        """Set the process state and notify callbacks (thread-safe)."""
        if self.state != new_state:
            self.state = new_state
            # Notify callbacks via monitor
            self.monitor.notify_status_change(new_state)

    def start(self):
        """Start the PTY-based interception."""
        if self.state == ProcessState.RUNNING:
            return  # Already running

        self._set_state(ProcessState.STARTING)

        # Clear the stop event for new start
        self._stop_event.clear()
        
        # Clear the process ready event for new start
        self.monitor.clear_ready_event()

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
        """Read output from the PTY in a separate thread."""
        while self.running and self.master_fd:
            try:
                # Use select to check for available data
                ready, _, _ = select.select([self.master_fd], [], [], 0.1)
                if ready:
                    data = os.read(self.master_fd, 4096)
                    if data:
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
            if self.monitor.check_process_ready_indicators(line):
                # Start a thread to update process info now that it's ready
                threading.Thread(
                    target=self.monitor.wait_for_process_ready_and_update_info,
                    args=(self.process,),
                    daemon=True
                ).start()
                # Trigger status callbacks to update UI immediately
                self.monitor.notify_status_change(self.state)
                
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
                    is_manual_stop = self._stop_event.is_set()

                    # Only set state if this is not a manual stop operation
                    if not is_manual_stop and self.state != ProcessState.STOPPING:
                        if exit_code == 0:
                            self._set_state(ProcessState.STOPPED)
                        else:
                            self._set_state(ProcessState.CRASHED)

                    # Handle auto-restart only if not manually stopping and auto-restart enabled
                    should_restart = (
                        self.auto_restart
                        and not is_manual_stop
                        and self.state not in [ProcessState.STOPPING, ProcessState.STOPPED]
                        and self.restart_count < self.max_restart_attempts
                    )

                    if should_restart:
                        self.restart_count += 1
                        self._set_state(ProcessState.RESTARTING)
                        time.sleep(self.restart_delay)
                        self.start()
                    break

                time.sleep(0.1)  # Small delay to prevent busy waiting
            except Exception:
                # Handle any unexpected errors in monitoring
                break

    def stop(self, force: bool = False):
        """Stop the PTY-based interception."""
        # Set manual stop event to prevent auto-restart
        self._stop_event.set()
        
        # Set state to stopping
        self._set_state(ProcessState.STOPPING)
        self.running = False

        # Terminate the process
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
        if self.master_fd:
            try:
                os.close(self.master_fd)
            except OSError:
                pass  # Already closed
            self.master_fd = None

        # Clean up threads
        if self.output_thread and self.output_thread.is_alive():
            self.output_thread.join(timeout=1)

        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1)

        # Clean up process reference
        self.process = None

        # Clear process information when stopping (memory, CPU, etc.)
        self.monitor.clear_process_info()

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
        if self.state == ProcessState.RUNNING:
            # Preserve port information during restart
            self.monitor.preserve_ports_for_restart()
            self.stop(force=force)
            # Wait for process to stop with timeout
            timeout = 0
            while (
                self.state not in [ProcessState.STOPPED, ProcessState.CRASHED]
                and timeout < 50
            ):
                time.sleep(0.1)
                timeout += 1

        # Reset restart counter and ensure clean state
        self.restart_count = 0
        self._set_state(ProcessState.STOPPED)

        self.start()

    def toggle_auto_restart(self):
        """Toggle auto-restart functionality."""
        self.auto_restart = not self.auto_restart
        return self.auto_restart

    def get_status(self):
        """Get current process status information (thread-safe)."""
        status = self.monitor.get_status_dict(
            self.process, 
            self.state, 
            self.auto_restart, 
            self.restart_count, 
            self.command
        )
        # Add max_restart_attempts for backward compatibility
        status["max_restart_attempts"] = self.max_restart_attempts
        return status
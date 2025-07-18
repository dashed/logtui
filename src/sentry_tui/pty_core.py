"""PTY-based process interception for sentry-tui."""

import fcntl
import os
import pty
import re
import select
import signal
import subprocess
import threading
import time
from typing import Callable, List, Optional

from .constants import ProcessState
from .utils import strip_ansi_codes


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
        self.last_known_ports = (
            set()
        )  # Preserve ports from previous process during restart
        self._process_ready_event = (
            threading.Event()
        )  # Signal when process is ready for port detection

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
                connections = proc.connections(kind="inet")
                for conn in connections:
                    if conn.status == psutil.CONN_LISTEN and conn.laddr:
                        ports.add(conn.laddr.port)

            except ImportError:
                # Method 2: Use netstat as fallback
                try:
                    # Use netstat to find listening ports for this PID
                    result = subprocess.run(
                        ["netstat", "-tulpn"], capture_output=True, text=True, timeout=2
                    )

                    for line in result.stdout.split("\n"):
                        if f"{pid}/" in line and "LISTEN" in line:
                            # Parse netstat output: tcp 0 0 127.0.0.1:8000 0.0.0.0:* LISTEN 12345/python
                            parts = line.split()
                            if len(parts) >= 4:
                                addr = parts[3]  # 127.0.0.1:8000
                                if ":" in addr:
                                    port_str = addr.split(":")[-1]
                                    try:
                                        port = int(port_str)
                                        if 1000 <= port <= 65535:
                                            ports.add(port)
                                    except ValueError:
                                        pass

                except (
                    subprocess.TimeoutExpired,
                    subprocess.CalledProcessError,
                    FileNotFoundError,
                ):
                    # Method 3: Use lsof as another fallback (macOS/Linux)
                    try:
                        result = subprocess.run(
                            ["lsof", "-Pan", "-p", str(pid), "-i"],
                            capture_output=True,
                            text=True,
                            timeout=2,
                        )

                        for line in result.stdout.split("\n"):
                            if "LISTEN" in line:
                                # Parse lsof output: python 12345 user 5u IPv4 TCP *:8000 (LISTEN)
                                parts = line.split()
                                for part in parts:
                                    if ":" in part and part.endswith("(LISTEN)"):
                                        port_str = part.split(":")[-1].replace(
                                            "(LISTEN)", ""
                                        )
                                        try:
                                            port = int(port_str)
                                            if 1000 <= port <= 65535:
                                                ports.add(port)
                                        except ValueError:
                                            pass

                    except (
                        subprocess.TimeoutExpired,
                        subprocess.CalledProcessError,
                        FileNotFoundError,
                    ):
                        pass

            # Update detected ports
            if ports:  # Only update if we actually found ports
                self.detected_ports = ports
                self.last_known_ports = ports.copy()  # Preserve for restart scenarios
            elif not self.detected_ports and self.last_known_ports:
                # If no ports detected but we have previous knowledge, keep the old ports temporarily
                # This helps during restart cycles where the process might not be fully ready
                self.detected_ports = self.last_known_ports.copy()

        except (OSError, Exception):
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
                "memory_mb": round(memory_info.rss / 1024 / 1024, 1),
                "cpu_percent": round(cpu_percent, 1)
                if cpu_percent > 0
                else None,  # Don't show 0% initially
                "status": proc.status(),
                "create_time": proc.create_time(),
            }
        except ImportError:
            # psutil not available, use basic info
            self.process_info = {
                "status": "running" if self.process.poll() is None else "terminated"
            }
        except Exception:
            # Process doesn't exist or no permission
            self.process_info = {}

    def _check_process_ready_indicators(self, line: str):
        """Check if log line indicates the process is ready for port detection."""
        if self._process_ready_event.is_set():
            return  # Already signaled

        clean_line = strip_ansi_codes(line).lower()

        # Common patterns that indicate a server/process is ready
        ready_patterns = [
            "running on",  # "Running on http://127.0.0.1:8000"
            "listening on",  # "Listening on port 8000"
            "server started",  # "Server started on port 8000"
            "development server",  # Django "Development server is running"
            "starting development",  # "Starting development server"
            "webpack compiled",  # Webpack ready
            "compiled successfully",  # Build completed
            "ready in",  # Various "Ready in XXXms" messages
            "listening at",  # "Listening at http://..."
            "bound to",  # Process bound to address
            "started server",  # "Started server on"
            "devserver.*ready",  # Sentry specific
        ]

        for pattern in ready_patterns:
            if re.search(pattern, clean_line):
                # Signal that the process appears ready
                self._process_ready_event.set()
                # Start a thread to update process info now that it's ready
                threading.Thread(
                    target=self._wait_for_process_ready_and_update_info, daemon=True
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

"""Process monitoring functionality for sentry-tui."""

import re
import subprocess
import threading
from typing import Callable, List, Optional, Set

from .constants import ProcessState
from .utils import strip_ansi_codes


class ProcessMonitor:
    """Handles process monitoring, port detection, and status tracking."""

    def __init__(self):
        self.detected_ports: Set[int] = set()
        self.process_info: dict = {}
        self.last_known_ports: Set[int] = set()
        self._process_ready_event = threading.Event()
        self.state_callbacks: List[Callable[[ProcessState], None]] = []
        self._state_lock = threading.Lock()

    def detect_ports_from_process(self, process) -> None:
        """Detect ports opened by the current process using system tools."""
        if not process:
            return
            
        try:
            pid = process.pid
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
            
        except (OSError, Exception):
            # Process doesn't exist or no permission
            self.detected_ports.clear()

    def wait_for_process_ready_and_update_info(self, process) -> None:
        """Wait for process to be ready and then update process information."""
        if not process:
            return
            
        # Wait for process ready signal with timeout
        if self._process_ready_event.wait(timeout=5.0):
            # Process is ready, proceed with port detection
            self.detect_ports_from_process(process)
        else:
            # Timeout - try anyway but preserve previous port info if available
            if self.last_known_ports and not self.detected_ports:
                self.detected_ports = self.last_known_ports.copy()
            self.detect_ports_from_process(process)
            
        self.update_basic_process_info(process)

    def update_process_info(self, process) -> None:
        """Update additional process information if available."""
        if not process:
            return
            
        # For regular updates (not startup), just update immediately
        self.detect_ports_from_process(process)
        self.update_basic_process_info(process)
            
    def update_basic_process_info(self, process) -> None:
        """Update basic process information like memory and CPU."""
        if not process:
            return
            
        try:
            # Try to get process info using psutil if available
            import psutil
            
            proc = psutil.Process(process.pid)
            
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
                'status': 'running' if process.poll() is None else 'terminated'
            }
        except Exception:
            # Process doesn't exist or no permission
            self.process_info = {}

    def check_process_ready_indicators(self, line: str) -> bool:
        """Check if log line indicates the process is ready for port detection.
        
        Returns:
            True if process readiness was detected and event was set
        """
        if self._process_ready_event.is_set():
            return False  # Already signaled
            
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
                return True
                
        return False

    def notify_status_change(self, state: ProcessState) -> None:
        """Notify all callbacks that status may have changed."""
        callbacks = []
        with self._state_lock:
            callbacks = self.state_callbacks.copy()
        
        # Notify callbacks outside the lock to prevent deadlocks
        for callback in callbacks:
            try:
                callback(state)
            except Exception:
                # Ignore callback errors to prevent affecting other callbacks
                pass

    def add_state_callback(self, callback: Callable[[ProcessState], None]) -> None:
        """Add a callback to be notified when process state changes (thread-safe)."""
        with self._state_lock:
            self.state_callbacks.append(callback)

    def remove_state_callback(self, callback: Callable[[ProcessState], None]) -> None:
        """Remove a state change callback (thread-safe)."""
        with self._state_lock:
            if callback in self.state_callbacks:
                self.state_callbacks.remove(callback)

    def clear_process_info(self) -> None:
        """Clear all process information (called when process stops)."""
        self.process_info.clear()
        self.detected_ports.clear()
        # Note: Keep last_known_ports for restart scenarios
        self._process_ready_event.clear()

    def preserve_ports_for_restart(self) -> Set[int]:
        """Preserve current ports for restart scenario and return them."""
        preserved_ports = self.detected_ports.copy()
        self.last_known_ports = preserved_ports
        return preserved_ports

    def is_process_ready(self) -> bool:
        """Check if the process ready event is set."""
        return self._process_ready_event.is_set()

    def clear_ready_event(self) -> None:
        """Clear the process ready event (called on new start)."""
        self._process_ready_event.clear()

    def get_status_dict(self, process, state: ProcessState, auto_restart: bool, 
                       restart_count: int, command: List[str]) -> dict:
        """Get current status information as a dictionary."""
        # Always update basic process info (memory is fast and doesn't need to wait)
        if process and state == ProcessState.RUNNING:
            self.update_basic_process_info(process)
            
            # Handle port detection based on readiness
            if not self._process_ready_event.is_set():
                # Use preserved port info if available, otherwise try immediate detection
                if self.last_known_ports and not self.detected_ports:
                    self.detected_ports = self.last_known_ports.copy()
                else:
                    # Try immediate port detection (may be empty initially)
                    self.detect_ports_from_process(process)
            else:
                # Process is ready, update ports normally
                self.detect_ports_from_process(process)
        
        return {
            "state": state,
            "auto_restart": auto_restart,
            "restart_count": restart_count,
            "pid": process.pid if process else None,
            "command": " ".join(command),
            "ports": sorted(list(self.detected_ports)),
            "process_info": self.process_info.copy(),
        }
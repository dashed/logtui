#!/usr/bin/env python3
"""
Dummy app that simulates Sentry devserver log output.
Logs output every few seconds with random intervals and handles Ctrl+C.
"""

import time
import random
import signal
from datetime import datetime
from typing import List

# ANSI color codes for service prefixes (simulating Sentry's color scheme)
SERVICE_COLORS = {
    "server": "\033[38;2;255;165;0m",  # Orange
    "worker": "\033[38;2;50;205;50m",  # Lime green
    "celery-beat": "\033[38;2;255;20;147m",  # Deep pink
    "webpack": "\033[38;2;135;206;235m",  # Sky blue
    "taskworker": "\033[38;2;218;165;32m",  # Golden rod
}

RESET = "\033[0m"

# Sample log messages to simulate real Sentry devserver output
LOG_MESSAGES = [
    ("server", "GET 200 /api/0/projects/"),
    ("server", "POST 201 /api/0/events/"),
    ("server", "GET 404 /api/0/nonexistent/"),
    ("server", "GET 200 /api/0/organizations/"),
    ("worker", "Task completed: sentry.tasks.process_event"),
    ("worker", "Processing event id=abc123..."),
    ("worker", "Task started: sentry.tasks.send_email"),
    ("worker", "Email sent to user@example.com"),
    ("celery-beat", "Scheduler: Running periodic task cleanup"),
    ("celery-beat", "Scheduler: Starting daily digest task"),
    ("webpack", "Compiled successfully in 1234ms"),
    (
        "webpack",
        "Hash: 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    ),
    ("webpack", "Built at: 2024-01-15 14:32:01"),
    ("taskworker", "Consuming from outcomes topic"),
    ("taskworker", "Processed 50 events from Kafka"),
    ("server", "Traceback (most recent call last):"),
    (
        "server",
        '  File "/app/sentry/api/endpoints/project_events.py", line 123, in get',
    ),
    ("server", '    raise ValueError("Invalid project ID")'),
    ("server", "ValueError: Invalid project ID"),
]


class DummyApp:
    def __init__(self):
        self.running = True
        self.log_count = 0

    def setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle Ctrl+C and other termination signals."""
        print(
            f"\n{self._get_timestamp()} Received signal {signum}, shutting down gracefully..."
        )
        self.running = False

    def _get_timestamp(self) -> str:
        """Get current timestamp in HH:MM:SS format (matching Sentry's format)."""
        return datetime.now().strftime("%H:%M:%S")

    def _colorize_service_name(self, service: str) -> str:
        """Add color to service name like Sentry does."""
        color = SERVICE_COLORS.get(service, "")
        return f"{color}{service:>12}{RESET}"

    def _format_log_line(self, service: str, message: str) -> str:
        """Format log line to match Sentry's devserver output format."""
        timestamp = self._get_timestamp()
        colored_service = self._colorize_service_name(service)

        # Add colored indicator bar (simulating Sentry's format)
        indicator_color = SERVICE_COLORS.get(service, "")
        indicator = f"{indicator_color} {RESET}"

        return f"{colored_service} {indicator} {timestamp} {message}"

    def _get_random_log_message(self) -> tuple[str, str]:
        """Get a random log message."""
        return random.choice(LOG_MESSAGES)

    def _add_some_multiline_logs(self) -> List[str]:
        """Occasionally add multi-line log entries (like tracebacks)."""
        if random.random() < 0.1:  # 10% chance of multiline log
            service, _ = self._get_random_log_message()
            lines = []
            lines.append(
                self._format_log_line(service, "Traceback (most recent call last):")
            )
            lines.append(
                self._format_log_line(
                    service,
                    '  File "/app/sentry/models/event.py", line 456, in process',
                )
            )
            lines.append(self._format_log_line(service, "    event.save()"))
            lines.append(
                self._format_log_line(
                    service, '  File "/app/sentry/models/event.py", line 234, in save'
                )
            )
            lines.append(
                self._format_log_line(
                    service, '    raise ValidationError("Invalid event data")'
                )
            )
            lines.append(
                self._format_log_line(service, "ValidationError: Invalid event data")
            )
            return lines
        return []

    def run(self):
        """Main loop that generates log output."""
        print(f"{self._get_timestamp()} Starting dummy Sentry devserver...")
        print(f"{self._get_timestamp()} Press Ctrl+C to stop")

        while self.running:
            try:
                # Add some multiline logs occasionally
                multiline_logs = self._add_some_multiline_logs()
                for line in multiline_logs:
                    print(line)
                    self.log_count += 1

                # Regular log message
                service, message = self._get_random_log_message()
                formatted_line = self._format_log_line(service, message)
                print(formatted_line)
                self.log_count += 1

                # Random delay between 0.5 and 3 seconds
                delay = random.uniform(0.5, 3.0)
                time.sleep(delay)

            except KeyboardInterrupt:
                # This shouldn't happen due to signal handler, but just in case
                break

        print(
            f"\n{self._get_timestamp()} Shutdown complete. Generated {self.log_count} log lines."
        )


def main():
    """Main entry point."""
    app = DummyApp()
    app.setup_signal_handlers()
    app.run()


if __name__ == "__main__":
    main()

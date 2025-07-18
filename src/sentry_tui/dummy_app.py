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

# Exact Sentry service colors from src/sentry/runner/formatting.py:18-24
SENTRY_SERVICE_COLORS = {
    "server": (108, 95, 199),
    "worker": (255, 194, 39),
    "webpack": (61, 116, 219),
    "cron": (255, 86, 124),
    "relay": (250, 71, 71),
    "getsentry-outcomes": (255, 119, 56),  # Orange for billing/outcomes
    "celery-beat": (255, 86, 124),  # Same as cron
    "taskworker": (255, 194, 39),  # Same as worker
}

# Convert RGB tuples to ANSI color codes
SERVICE_COLORS = {
    service: f"\033[38;2;{r};{g};{b}m"
    for service, (r, g, b) in SENTRY_SERVICE_COLORS.items()
}

RESET = "\033[0m"

# Sample log messages in exact Sentry HumanRenderer format: [LEVEL] module.name: message
LOG_MESSAGES = [
    ("server", "INFO", "sentry.web.frontend", "GET 200 /api/0/projects/"),
    ("server", "INFO", "sentry.web.frontend", "POST 201 /api/0/events/"),
    ("server", "WARNING", "sentry.web.frontend", "GET 404 /api/0/nonexistent/"),
    ("server", "INFO", "sentry.web.api", "GET 200 /api/0/organizations/"),
    ("worker", "INFO", "sentry.tasks.process_event", "Task completed: process_event"),
    (
        "worker",
        "DEBUG",
        "sentry.tasks.process_event",
        "Processing event id=abc123def456",
    ),
    ("worker", "INFO", "sentry.tasks.email", "Task started: send_email"),
    ("worker", "INFO", "sentry.tasks.email", "Email sent to user@example.com"),
    ("celery-beat", "INFO", "sentry.tasks.cleanup", "Running periodic task cleanup"),
    ("celery-beat", "INFO", "sentry.tasks.digest", "Starting daily digest task"),
    ("webpack", "INFO", "webpack.compiler", "Compiled successfully in 1234ms"),
    (
        "webpack",
        "DEBUG",
        "webpack.compiler",
        "Hash: 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
    ),
    ("webpack", "INFO", "webpack.compiler", "Built at: 2024-01-15 14:32:01"),
    ("taskworker", "INFO", "sentry.tasks.kafka", "Consuming from outcomes topic"),
    ("taskworker", "DEBUG", "sentry.tasks.kafka", "Processed 50 events from Kafka"),
    (
        "getsentry-outcomes",
        "INFO",
        "getsentry.billing.outcomes",
        "Processing billing outcomes",
    ),
    (
        "getsentry-outcomes",
        "DEBUG",
        "getsentry.billing.outcomes",
        "Outcome: event processed",
    ),
    (
        "server",
        "ERROR",
        "sentry.api.endpoints.project_events",
        "Traceback (most recent call last):",
    ),
    (
        "server",
        "ERROR",
        "sentry.api.endpoints.project_events",
        '  File "/app/sentry/api/endpoints/project_events.py", line 123, in get',
    ),
    (
        "server",
        "ERROR",
        "sentry.api.endpoints.project_events",
        '    raise ValueError("Invalid project ID")',
    ),
    (
        "server",
        "ERROR",
        "sentry.api.endpoints.project_events",
        "ValueError: Invalid project ID",
    ),
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

    def _format_log_line(
        self, service: str, level: str, module: str, message: str
    ) -> str:
        """Format log line to match exact Sentry SentryPrinter + HumanRenderer format.

        Final format: {colored_service_name} {colored_indicator} HH:MM:SS [LEVEL] module.name: message
        """
        timestamp = self._get_timestamp()

        # Format the HumanRenderer part: HH:MM:SS [LEVEL] module.name: message
        human_format = f"{timestamp} [{level}] {module}: {message}"

        # Add SentryPrinter service prefix with exact format from formatting.py:110-118
        service_color = SERVICE_COLORS.get(service, "")
        name_colored = f"{service_color}{service:>12}{RESET}"
        indicator_colored = f"{service_color} {RESET}"

        return f"{name_colored} {indicator_colored} {human_format}"

    def _get_random_log_message(self) -> tuple[str, str, str, str]:
        """Get a random log message."""
        return random.choice(LOG_MESSAGES)

    def _add_some_multiline_logs(self) -> List[str]:
        """Occasionally add multi-line log entries (like tracebacks)."""
        if random.random() < 0.1:  # 10% chance of multiline log
            service, _, _, _ = self._get_random_log_message()
            lines = []
            lines.append(
                self._format_log_line(
                    service,
                    "ERROR",
                    "sentry.models.event",
                    "Traceback (most recent call last):",
                )
            )
            lines.append(
                self._format_log_line(
                    service,
                    "ERROR",
                    "sentry.models.event",
                    '  File "/app/sentry/models/event.py", line 456, in process',
                )
            )
            lines.append(
                self._format_log_line(
                    service, "ERROR", "sentry.models.event", "    event.save()"
                )
            )
            lines.append(
                self._format_log_line(
                    service,
                    "ERROR",
                    "sentry.models.event",
                    '  File "/app/sentry/models/event.py", line 234, in save',
                )
            )
            lines.append(
                self._format_log_line(
                    service,
                    "ERROR",
                    "sentry.models.event",
                    '    raise ValidationError("Invalid event data")',
                )
            )
            lines.append(
                self._format_log_line(
                    service,
                    "ERROR",
                    "sentry.models.event",
                    "ValidationError: Invalid event data",
                )
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
                service, level, module, message = self._get_random_log_message()
                formatted_line = self._format_log_line(service, level, module, message)
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

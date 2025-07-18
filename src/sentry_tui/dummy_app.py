#!/usr/bin/env python3
"""
Dummy app that simulates Sentry devserver log output in real Honcho format.

Real Sentry devserver format: HH:MM:SS service_name | log_message

Source Code References:
- Honcho process manager: /Users/me/aaa/sentry/sentry/src/sentry/runner/commands/devserver.py:507-509
- SentryPrinter formatting: /Users/me/aaa/sentry/sentry/src/sentry/runner/formatting.py:78-120
- Service definitions: /Users/me/aaa/sentry/sentry/src/sentry/runner/commands/devserver.py:21-27

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

# Sample log messages in Sentry Honcho format: service_name and raw message content
# Based on real devserver logs and source code analysis
# Source: /Users/me/aaa/sentry/sentry/src/sentry/runner/commands/devserver.py:21-27 (service names)
LOG_MESSAGES = [
    ("system", "webpack started (pid=83946)"),
    ("system", "server started (pid=83945)"),
    ("server", "Using configuration 'getsentry.conf.settings.dev'"),
    ("server", "*** Starting uWSGI 2.0.28 (64bit) on [Mon Jan 15 06:40:52 2024] ***"),
    (
        "server",
        "compiled with version: Apple LLVM 15.0.0 (clang-1500.3.9.4) on 31 October 2024 18:20:36",
    ),
    ("server", "os: Darwin-24.3.0 Darwin Kernel Version 24.3.0"),
    ("server", "detected number of CPU cores: 10"),
    ("server", "current working directory: /Users/me/aaa/sentry/sentry"),
    ("server", "GET 200 /api/0/projects/ http/1.1 1234"),
    ("server", "POST 201 /api/0/events/ http/1.1 2345"),
    ("server", "GET 404 /api/0/nonexistent/ http/1.1 123"),
    (
        "webpack",
        "<i> [webpack-dev-server] [HPM] Proxy created: /api/store/**,/api/{1..9}*({0..9})/**,/api/0/relays/outcomes/**  -> http://127.0.0.1:7899",
    ),
    (
        "webpack",
        "<i> [webpack-dev-server] [HPM] Proxy created: !/_static/dist/sentry/**  -> http://127.0.0.1:8001/",
    ),
    (
        "webpack",
        "(node:83946) ExperimentalWarning: Type Stripping is an experimental feature and might change at any time",
    ),
    ("webpack", "<i> [webpack-dev-server] Project is running at:"),
    ("webpack", "<i> [webpack-dev-server] Loopback: http://127.0.0.1:8000/"),
    (
        "webpack",
        "<i> [webpack-dev-server] Content not from webpack is served from './src/sentry/static/sentry' directory",
    ),
    (
        "worker",
        "[2024-01-15 14:32:01,123: INFO/MainProcess] Connected to redis://127.0.0.1:6379/0",
    ),
    ("worker", "[2024-01-15 14:32:01,456: INFO/MainProcess] celery@hostname ready."),
    (
        "worker",
        "[2024-01-15 14:32:01,789: INFO/ForkPoolWorker-1] Task sentry.tasks.process_event[abc-123-def] succeeded in 0.123s",
    ),
    (
        "celery-beat",
        "[2024-01-15 14:32:00,000: INFO/MainProcess] Scheduler: Sending due task cleanup (sentry.tasks.cleanup)",
    ),
    (
        "celery-beat",
        "[2024-01-15 14:32:00,100: INFO/MainProcess] Scheduler: Sending due task digest (sentry.tasks.digest)",
    ),
    ("taskworker", "Starting task worker for outcomes processing"),
    ("taskworker", "Consuming from kafka topic outcomes-consumer"),
    ("taskworker", "Processed 50 events from Kafka in batch"),
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
        """Format log line to match exact Sentry Honcho format.

        Real format: HH:MM:SS service_name | log_message

        Source Code References:
        - Honcho adds timestamp: honcho.printer.Printer (external library)
        - SentryPrinter format: /Users/me/aaa/sentry/sentry/src/sentry/runner/formatting.py:110-118
        - Service colors: /Users/me/aaa/sentry/sentry/src/sentry/runner/formatting.py:18-24
        """
        timestamp = self._get_timestamp()

        # Add ANSI colors to match SentryPrinter behavior
        service_color = SERVICE_COLORS.get(service, "")
        service_colored = f"{service_color}{service}{RESET}"

        return f"{timestamp} {service_colored} | {message}"

    def _get_random_log_message(self) -> tuple[str, str]:
        """Get a random log message."""
        return random.choice(LOG_MESSAGES)

    def _add_some_multiline_logs(self) -> List[str]:
        """Occasionally add multi-line log entries (like tracebacks)."""
        if random.random() < 0.1:  # 10% chance of multiline log
            service, _ = self._get_random_log_message()
            lines = []
            lines.append(
                self._format_log_line(
                    service,
                    "Traceback (most recent call last):",
                )
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
                    service,
                    '  File "/app/sentry/models/event.py", line 234, in save',
                )
            )
            lines.append(
                self._format_log_line(
                    service,
                    '    raise ValidationError("Invalid event data")',
                )
            )
            lines.append(
                self._format_log_line(
                    service,
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

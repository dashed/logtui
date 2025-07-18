"""Constants and enums for sentry-tui."""

import re
from enum import Enum


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


# Sentry service color mapping based on actual Sentry devserver source code
# Source: /Users/me/aaa/sentry/sentry/src/sentry/runner/formatting.py:18-24
SENTRY_SERVICE_COLORS = {
    "server": "purple",      # Django web server
    "worker": "yellow",      # Celery worker  
    "webpack": "blue",       # Frontend build process
    "celery-beat": "magenta", # Periodic task scheduler
    "relay": "red",          # Relay service
    "getsentry-outcomes": "bright_yellow",  # Billing/outcomes service
    "system": "cyan",        # System messages
    "taskworker": "green",   # Task worker processes
}
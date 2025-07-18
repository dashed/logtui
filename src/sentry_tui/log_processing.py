"""Log processing and parsing functionality."""

import re
import time
from typing import Optional

from .constants import SENTRY_SERVICE_COLORS
from .utils import strip_ansi_codes


class LogLine:
    """Represents a single log line with metadata."""

    def __init__(self, content: str, timestamp: Optional[float] = None):
        self.content = content
        self.timestamp = timestamp or time.time()
        self.service = self._extract_service()
        self.level = self._extract_level()
        self.module_name = self._extract_module_name()
        self.message = self._extract_message()

    def _extract_service(self) -> str:
        """Extract service name from Sentry Honcho format.

        Format: HH:MM:SS service_name | log_message

        Examples:
        - "06:40:47 system  | webpack started (pid=83946)"
        - "06:40:48 server  | Using configuration 'getsentry.conf.settings.dev'"
        - "06:40:51 webpack | <i> [webpack-dev-server] [HPM] Proxy created..."

        Source Code References:
        - Honcho process manager: /Users/me/aaa/sentry/sentry/src/sentry/runner/commands/devserver.py:507-509
        - SentryPrinter format logic: /Users/me/aaa/sentry/sentry/src/sentry/runner/formatting.py:78-120
        - Service names from daemons: /Users/me/aaa/sentry/sentry/src/sentry/runner/commands/devserver.py:21-27
        - Color scheme: /Users/me/aaa/sentry/sentry/src/sentry/runner/formatting.py:18-24
        """
        # Remove ANSI color codes first
        clean_content = strip_ansi_codes(self.content)

        # Look for pattern: HH:MM:SS service_name |
        match = re.match(r"^\d{2}:\d{2}:\d{2}\s+([a-zA-Z0-9._-]+)\s*\|", clean_content)
        if match:
            return match.group(1).strip()

        # Fallback: try to find service name in known services
        for service in SENTRY_SERVICE_COLORS.keys():
            if service in clean_content:
                return service

        return "unknown"

    def _extract_level(self) -> str:
        """Extract log level from Sentry Honcho format: HH:MM:SS service_name | log_message

        Since Honcho format doesn't include explicit log levels, we infer from content.

        Source Code References:
        - Honcho doesn't add log levels: /Users/me/aaa/sentry/sentry/src/sentry/runner/formatting.py:110-118
        - Original services just output raw logs to Honcho
        - Log level inference based on common error patterns
        """
        # Remove ANSI color codes first
        clean_content = strip_ansi_codes(self.content)

        # Look for common error indicators
        content_lower = clean_content.lower()
        if any(
            word in content_lower
            for word in ["error", "exception", "traceback", "failed", "critical"]
        ):
            return "ERROR"
        elif any(word in content_lower for word in ["warning", "warn", "deprecated"]):
            return "WARNING"
        elif any(word in content_lower for word in ["debug"]):
            return "DEBUG"

        return "INFO"  # Default level

    def _extract_module_name(self) -> str:
        """Extract module name from Sentry Honcho format: HH:MM:SS service_name | log_message

        Since Honcho format doesn't include explicit module names, we use the service name.

        Source Code References:
        - Honcho format limitation: /Users/me/aaa/sentry/sentry/src/sentry/runner/formatting.py:110-118
        - Service names represent the module/daemon: /Users/me/aaa/sentry/sentry/src/sentry/runner/commands/devserver.py:21-27
        """
        return self.service

    def _extract_message(self) -> str:
        """Extract message content from Sentry Honcho format: HH:MM:SS service_name | log_message

        Source Code References:
        - Honcho format: /Users/me/aaa/sentry/sentry/src/sentry/runner/formatting.py:110-118
        - Message is everything after the pipe separator
        """
        # Remove ANSI color codes first
        clean_content = strip_ansi_codes(self.content)

        # Look for pattern: HH:MM:SS service_name | message
        match = re.match(
            r"^\d{2}:\d{2}:\d{2}\s+[a-zA-Z0-9._-]+\s*\|\s*(.*)", clean_content
        )
        if match:
            return match.group(1).strip()

        # Fallback: return the entire clean content
        return clean_content.strip()

"""Tests for LogLine class."""

import pytest
import time
from sentry_tui.pty_interceptor import LogLine


class TestLogLine:
    """Test cases for LogLine class."""

    def test_log_line_creation_with_content(self):
        """Test LogLine creation with content."""
        content = "\x1b[38;2;108;95;199m      server\x1b[0m \x1b[38;2;108;95;199m \x1b[0m 14:32:01 [INFO] sentry.web.frontend: GET 200 /api/0/projects/"
        log_line = LogLine(content)
        
        assert log_line.content == content
        assert isinstance(log_line.timestamp, float)
        assert log_line.timestamp > 0

    def test_log_line_creation_with_custom_timestamp(self):
        """Test LogLine creation with custom timestamp."""
        content = "Test log line"
        custom_timestamp = 1234567890.0
        log_line = LogLine(content, timestamp=custom_timestamp)
        
        assert log_line.content == content
        assert log_line.timestamp == custom_timestamp

    def test_log_line_creation_with_none_timestamp(self):
        """Test LogLine creation with None timestamp uses current time."""
        content = "Test log line"
        before_creation = time.time()
        log_line = LogLine(content, timestamp=None)
        after_creation = time.time()
        
        assert log_line.content == content
        assert before_creation <= log_line.timestamp <= after_creation

    def test_service_extraction_server(self):
        """Test service extraction for server logs."""
        # Sentry format: {colored_service_name} {colored_indicator} HH:MM:SS [LEVEL] module.name: message
        content = "\x1b[38;2;108;95;199m      server\x1b[0m \x1b[38;2;108;95;199m \x1b[0m 14:32:01 [INFO] sentry.web.frontend: GET 200 /api/0/projects/"
        log_line = LogLine(content)
        assert log_line.service == "server"

    def test_service_extraction_worker(self):
        """Test service extraction for worker logs."""
        content = "\x1b[38;2;255;194;39m      worker\x1b[0m \x1b[38;2;255;194;39m \x1b[0m 14:32:01 [INFO] sentry.tasks.process_event: Task completed"
        log_line = LogLine(content)
        assert log_line.service == "worker"

    def test_service_extraction_celery_beat(self):
        """Test service extraction for celery-beat logs."""
        content = "\x1b[38;2;255;86;124m  celery-beat\x1b[0m \x1b[38;2;255;86;124m \x1b[0m 14:32:01 [INFO] sentry.tasks.cleanup: Running periodic task cleanup"
        log_line = LogLine(content)
        assert log_line.service == "celery-beat"

    def test_service_extraction_webpack(self):
        """Test service extraction for webpack logs."""
        content = "\x1b[38;2;61;116;219m     webpack\x1b[0m \x1b[38;2;61;116;219m \x1b[0m 14:32:01 [INFO] webpack.compiler: Compiled successfully in 1234ms"
        log_line = LogLine(content)
        assert log_line.service == "webpack"

    def test_service_extraction_taskworker(self):
        """Test service extraction for taskworker logs."""
        content = "\x1b[38;2;255;194;39m  taskworker\x1b[0m \x1b[38;2;255;194;39m \x1b[0m 14:32:01 [DEBUG] sentry.tasks.kafka: Processing event id=abc123"
        log_line = LogLine(content)
        assert log_line.service == "taskworker"

    def test_service_extraction_unknown_format(self):
        """Test service extraction for unknown log format."""
        content = "This is not a standard log format"
        log_line = LogLine(content)
        assert log_line.service == "unknown"

    def test_service_extraction_empty_content(self):
        """Test service extraction for empty content."""
        content = ""
        log_line = LogLine(content)
        assert log_line.service == "unknown"

    def test_service_extraction_getsentry_outcomes(self):
        """Test service extraction for getsentry-outcomes logs."""
        content = "\x1b[38;2;255;119;56mgetsentry-outcomes\x1b[0m \x1b[38;2;255;119;56m \x1b[0m 14:32:01 [INFO] getsentry.billing.outcomes: Processing billing outcomes"
        log_line = LogLine(content)
        assert log_line.service == "getsentry-outcomes"

    def test_service_extraction_without_ansi_codes(self):
        """Test service extraction when ANSI codes are stripped."""
        content = "      server  14:32:01 [INFO] sentry.web.frontend: GET 200 /api/0/projects/"
        log_line = LogLine(content)
        assert log_line.service == "server"

    def test_level_extraction_info(self):
        """Test log level extraction for INFO level."""
        content = "\x1b[38;2;108;95;199m      server\x1b[0m \x1b[38;2;108;95;199m \x1b[0m 14:32:01 [INFO] sentry.web.frontend: GET 200 /api/0/projects/"
        log_line = LogLine(content)
        assert log_line.level == "INFO"

    def test_level_extraction_error(self):
        """Test log level extraction for ERROR level."""
        content = "\x1b[38;2;108;95;199m      server\x1b[0m \x1b[38;2;108;95;199m \x1b[0m 14:32:01 [ERROR] sentry.api.endpoints: ValueError: Invalid project ID"
        log_line = LogLine(content)
        assert log_line.level == "ERROR"

    def test_module_name_extraction(self):
        """Test module name extraction from log content."""
        content = "\x1b[38;2;108;95;199m      server\x1b[0m \x1b[38;2;108;95;199m \x1b[0m 14:32:01 [INFO] sentry.web.frontend: GET 200 /api/0/projects/"
        log_line = LogLine(content)
        assert log_line.module_name == "sentry.web.frontend"

    def test_message_extraction(self):
        """Test message extraction from log content."""
        content = "\x1b[38;2;108;95;199m      server\x1b[0m \x1b[38;2;108;95;199m \x1b[0m 14:32:01 [INFO] sentry.web.frontend: GET 200 /api/0/projects/"
        log_line = LogLine(content)
        assert log_line.message == "GET 200 /api/0/projects/"

    def test_log_line_all_properties(self):
        """Test that LogLine objects have all expected properties."""
        content = "\x1b[38;2;108;95;199m      server\x1b[0m \x1b[38;2;108;95;199m \x1b[0m 14:32:01 [INFO] sentry.web.frontend: GET 200 /api/0/projects/"
        log_line = LogLine(content)
        
        # Should be able to access all properties
        assert hasattr(log_line, 'content')
        assert hasattr(log_line, 'timestamp')
        assert hasattr(log_line, 'service')
        assert hasattr(log_line, 'level')
        assert hasattr(log_line, 'module_name')
        assert hasattr(log_line, 'message')
        
        # Content should be preserved exactly
        assert log_line.content == content
        # Parsed properties should be correct
        assert log_line.service == "server"
        assert log_line.level == "INFO"
        assert log_line.module_name == "sentry.web.frontend"
        assert log_line.message == "GET 200 /api/0/projects/"
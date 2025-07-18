"""Tests for LogLine class."""

import time
from sentry_tui.pty_interceptor import LogLine


class TestLogLine:
    """Test cases for LogLine class."""

    def test_log_line_creation_with_content(self):
        """Test LogLine creation with content."""
        # Real Sentry Honcho format: HH:MM:SS service_name | log_message
        content = "14:32:01 \x1b[38;2;108;95;199mserver\x1b[0m | GET 200 /api/0/projects/ http/1.1 1234"
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
        # Real Sentry Honcho format: HH:MM:SS service_name | log_message
        content = "14:32:01 \x1b[38;2;108;95;199mserver\x1b[0m | GET 200 /api/0/projects/ http/1.1 1234"
        log_line = LogLine(content)
        assert log_line.service == "server"

    def test_service_extraction_worker(self):
        """Test service extraction for worker logs."""
        content = "14:32:01 \x1b[38;2;255;194;39mworker\x1b[0m | [2024-01-15 14:32:01,123: INFO/MainProcess] celery@hostname ready."
        log_line = LogLine(content)
        assert log_line.service == "worker"

    def test_service_extraction_celery_beat(self):
        """Test service extraction for celery-beat logs."""
        content = "14:32:01 \x1b[38;2;255;86;124mcelery-beat\x1b[0m | [2024-01-15 14:32:00,000: INFO/MainProcess] Scheduler: Sending due task cleanup"
        log_line = LogLine(content)
        assert log_line.service == "celery-beat"

    def test_service_extraction_webpack(self):
        """Test service extraction for webpack logs."""
        content = "14:32:01 \x1b[38;2;61;116;219mwebpack\x1b[0m | <i> [webpack-dev-server] Project is running at:"
        log_line = LogLine(content)
        assert log_line.service == "webpack"

    def test_service_extraction_taskworker(self):
        """Test service extraction for taskworker logs."""
        content = "14:32:01 \x1b[38;2;255;194;39mtaskworker\x1b[0m | Starting task worker for outcomes processing"
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
        content = "14:32:01 \x1b[38;2;255;119;56mgetsentry-outcomes\x1b[0m | Processing billing outcomes"
        log_line = LogLine(content)
        assert log_line.service == "getsentry-outcomes"

    def test_service_extraction_without_ansi_codes(self):
        """Test service extraction when ANSI codes are stripped."""
        content = "14:32:01 server | GET 200 /api/0/projects/ http/1.1 1234"
        log_line = LogLine(content)
        assert log_line.service == "server"

    def test_level_extraction_info(self):
        """Test log level extraction for INFO level (inferred from content)."""
        content = "14:32:01 \x1b[38;2;108;95;199mserver\x1b[0m | GET 200 /api/0/projects/ http/1.1 1234"
        log_line = LogLine(content)
        assert log_line.level == "INFO"  # Default level when no error indicators

    def test_level_extraction_error(self):
        """Test log level extraction for ERROR level (inferred from content)."""
        content = "14:32:01 \x1b[38;2;108;95;199mserver\x1b[0m | Traceback (most recent call last):"
        log_line = LogLine(content)
        assert log_line.level == "ERROR"  # Inferred from 'traceback' keyword

    def test_module_name_extraction(self):
        """Test module name extraction from log content (uses service name in Honcho format)."""
        content = "14:32:01 \x1b[38;2;108;95;199mserver\x1b[0m | GET 200 /api/0/projects/ http/1.1 1234"
        log_line = LogLine(content)
        assert (
            log_line.module_name == "server"
        )  # Module name is service name in Honcho format

    def test_message_extraction(self):
        """Test message extraction from log content."""
        content = "14:32:01 \x1b[38;2;108;95;199mserver\x1b[0m | GET 200 /api/0/projects/ http/1.1 1234"
        log_line = LogLine(content)
        assert log_line.message == "GET 200 /api/0/projects/ http/1.1 1234"

    def test_log_line_all_properties(self):
        """Test that LogLine objects have all expected properties."""
        content = "14:32:01 \x1b[38;2;108;95;199mserver\x1b[0m | GET 200 /api/0/projects/ http/1.1 1234"
        log_line = LogLine(content)

        # Should be able to access all properties
        assert hasattr(log_line, "content")
        assert hasattr(log_line, "timestamp")
        assert hasattr(log_line, "service")
        assert hasattr(log_line, "level")
        assert hasattr(log_line, "module_name")
        assert hasattr(log_line, "message")

        # Content should be preserved exactly
        assert log_line.content == content
        # Parsed properties should be correct (Honcho format uses service name as module name)
        assert log_line.service == "server"
        assert log_line.level == "INFO"
        assert (
            log_line.module_name == "server"
        )  # Module name is service name in Honcho format
        assert log_line.message == "GET 200 /api/0/projects/ http/1.1 1234"

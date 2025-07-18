"""Tests for LogLine class."""

import pytest
import time
from sentry_tui.pty_interceptor import LogLine


class TestLogLine:
    """Test cases for LogLine class."""

    def test_log_line_creation_with_content(self):
        """Test LogLine creation with content."""
        content = "      server  14:32:01 GET 200 /api/0/projects/"
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
        content = "      server  14:32:01 GET 200 /api/0/projects/"
        log_line = LogLine(content)
        assert log_line.service == "server"

    def test_service_extraction_worker(self):
        """Test service extraction for worker logs."""
        content = "      worker  14:32:01 Task completed: sentry.tasks.process_event"
        log_line = LogLine(content)
        assert log_line.service == "worker"

    def test_service_extraction_celery_beat(self):
        """Test service extraction for celery-beat logs."""
        content = "  celery-beat  14:32:01 Scheduler: Running periodic task cleanup"
        log_line = LogLine(content)
        assert log_line.service == "celery-beat"

    def test_service_extraction_webpack(self):
        """Test service extraction for webpack logs."""
        content = "     webpack  14:32:01 Compiled successfully in 1234ms"
        log_line = LogLine(content)
        assert log_line.service == "webpack"

    def test_service_extraction_taskworker(self):
        """Test service extraction for taskworker logs."""
        content = "  taskworker  14:32:01 Processing event id=abc123..."
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

    def test_service_extraction_no_pipe_separator(self):
        """Test service extraction when there's no pipe separator."""
        content = "server 14:32:01 GET 200 /api/0/projects/"
        log_line = LogLine(content)
        assert log_line.service == "server"

    def test_service_extraction_with_extra_whitespace(self):
        """Test service extraction with extra whitespace."""
        content = "        server     14:32:01 GET 200 /api/0/projects/"
        log_line = LogLine(content)
        assert log_line.service == "server"  # Should extract service name correctly

    def test_service_extraction_with_pipe_but_no_service(self):
        """Test service extraction with pipe but no service name."""
        content = "   | 14:32:01 GET 200 /api/0/projects/"
        log_line = LogLine(content)
        assert log_line.service == "unknown"

    def test_service_extraction_numeric_service_name(self):
        """Test service extraction with numeric service name."""
        content = "    server123  14:32:01 GET 200 /api/0/projects/"
        log_line = LogLine(content)
        assert log_line.service == "server123"

    def test_service_extraction_underscore_service_name(self):
        """Test service extraction with underscore in service name."""
        content = "  task_worker  14:32:01 Processing event"
        log_line = LogLine(content)
        assert log_line.service == "task_worker"

    @pytest.mark.parametrize("service_name", [
        "server", "worker", "celery-beat", "webpack", "taskworker",
        "server123", "task_worker", "test_service", "a1b2c3"
    ])
    def test_service_extraction_parametrized(self, service_name):
        """Test service extraction with various service names."""
        content = f"  {service_name}  14:32:01 Some log message"
        log_line = LogLine(content)
        assert log_line.service == service_name

    def test_log_line_string_representation(self):
        """Test that LogLine objects can be created and accessed properly."""
        content = "      server  14:32:01 GET 200 /api/0/projects/"
        log_line = LogLine(content)
        
        # Should be able to access all properties
        assert hasattr(log_line, 'content')
        assert hasattr(log_line, 'timestamp')
        assert hasattr(log_line, 'service')
        
        # Content should be preserved exactly
        assert log_line.content == content
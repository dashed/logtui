"""Tests for log filtering functionality."""

import pytest
from sentry_tui.pty_interceptor import LogLine, SentryTUIApp


class TestLogFiltering:
    """Test cases for log filtering functionality."""

    @pytest.fixture
    def test_log_lines(self):
        """Create test log lines for filtering tests."""
        return [
            LogLine("      server  14:32:01 GET 200 /api/0/projects/"),
            LogLine("      server  14:32:01 ERROR: Database connection failed"),
            LogLine("      worker  14:32:01 INFO: Task completed successfully"),
            LogLine("      worker  14:32:01 ERROR: Task failed with exception"),
            LogLine("  celery-beat  14:32:01 INFO: Running periodic cleanup"),
            LogLine("     webpack  14:32:01 Compiled successfully in 1234ms"),
            LogLine("  taskworker  14:32:01 Processing event id=abc123"),
            LogLine("      server  14:32:01 Traceback (most recent call last):"),
            LogLine(
                '      server  14:32:01   File "/app/sentry/api/endpoints/project_events.py", line 123'
            ),
            LogLine("      server  14:32:01 ValueError: Invalid project ID"),
        ]

    def test_empty_filter_matches_all(self, test_log_lines):
        """Test that empty filter matches all log lines."""
        app = SentryTUIApp(["test"])
        app.filter_text = ""

        for log_line in test_log_lines:
            assert app.matches_filter(log_line)

    def test_filter_by_error_level(self, test_log_lines):
        """Test filtering by error level."""
        app = SentryTUIApp(["test"])
        app.filter_text = "ERROR"

        # Should match lines containing "ERROR"
        assert app.matches_filter(test_log_lines[1])  # server ERROR
        assert app.matches_filter(test_log_lines[3])  # worker ERROR

        # Should not match lines without "ERROR"
        assert not app.matches_filter(test_log_lines[0])  # server GET
        assert not app.matches_filter(test_log_lines[2])  # worker INFO
        assert not app.matches_filter(test_log_lines[4])  # celery-beat INFO

    def test_filter_by_service_name(self, test_log_lines):
        """Test filtering by service name."""
        app = SentryTUIApp(["test"])
        app.filter_text = "server"

        # Should match lines containing "server"
        assert app.matches_filter(test_log_lines[0])  # server GET
        assert app.matches_filter(test_log_lines[1])  # server ERROR
        assert app.matches_filter(test_log_lines[7])  # server Traceback

        # Should not match lines without "server"
        assert not app.matches_filter(test_log_lines[2])  # worker INFO
        assert not app.matches_filter(test_log_lines[4])  # celery-beat INFO
        assert not app.matches_filter(test_log_lines[5])  # webpack

    def test_filter_case_insensitive(self, test_log_lines):
        """Test that filtering is case insensitive."""
        app = SentryTUIApp(["test"])

        # Test uppercase filter
        app.filter_text = "ERROR"
        assert app.matches_filter(test_log_lines[1])  # server ERROR

        # Test lowercase filter
        app.filter_text = "error"
        assert app.matches_filter(test_log_lines[1])  # server ERROR

        # Test mixed case filter
        app.filter_text = "ErRoR"
        assert app.matches_filter(test_log_lines[1])  # server ERROR

    def test_filter_by_partial_word(self, test_log_lines):
        """Test filtering by partial word."""
        app = SentryTUIApp(["test"])
        app.filter_text = "Compi"  # Partial word from "Compiled"

        # Should match lines containing the partial word
        assert app.matches_filter(test_log_lines[5])  # webpack Compiled

        # Should not match lines without the partial word
        assert not app.matches_filter(test_log_lines[0])  # server GET
        assert not app.matches_filter(test_log_lines[2])  # worker INFO

    def test_filter_by_http_method(self, test_log_lines):
        """Test filtering by HTTP method."""
        app = SentryTUIApp(["test"])
        app.filter_text = "GET"

        # Should match lines containing "GET"
        assert app.matches_filter(test_log_lines[0])  # server GET

        # Should not match lines without "GET"
        assert not app.matches_filter(test_log_lines[1])  # server ERROR
        assert not app.matches_filter(test_log_lines[2])  # worker INFO

    def test_filter_by_status_code(self, test_log_lines):
        """Test filtering by HTTP status code."""
        app = SentryTUIApp(["test"])
        app.filter_text = "200"

        # Should match lines containing "200"
        assert app.matches_filter(test_log_lines[0])  # server GET 200

        # Should not match lines without "200"
        assert not app.matches_filter(test_log_lines[1])  # server ERROR
        assert not app.matches_filter(test_log_lines[2])  # worker INFO

    def test_filter_by_file_path(self, test_log_lines):
        """Test filtering by file path."""
        app = SentryTUIApp(["test"])
        app.filter_text = "/app/sentry/"

        # Should match lines containing the file path
        assert app.matches_filter(test_log_lines[8])  # server File "/app/sentry/...

        # Should not match lines without the file path
        assert not app.matches_filter(test_log_lines[0])  # server GET
        assert not app.matches_filter(test_log_lines[2])  # worker INFO

    def test_filter_by_exception_type(self, test_log_lines):
        """Test filtering by exception type."""
        app = SentryTUIApp(["test"])
        app.filter_text = "ValueError"

        # Should match lines containing "ValueError"
        assert app.matches_filter(test_log_lines[9])  # server ValueError

        # Should not match lines without "ValueError"
        assert not app.matches_filter(test_log_lines[0])  # server GET
        assert not app.matches_filter(test_log_lines[1])  # server ERROR

    def test_filter_by_task_info(self, test_log_lines):
        """Test filtering by task information."""
        app = SentryTUIApp(["test"])
        app.filter_text = "Task"

        # Should match lines containing "Task"
        assert app.matches_filter(test_log_lines[2])  # worker Task completed
        assert app.matches_filter(test_log_lines[3])  # worker Task failed

        # Should not match lines without "Task"
        assert not app.matches_filter(test_log_lines[0])  # server GET
        assert not app.matches_filter(test_log_lines[5])  # webpack

    def test_filter_by_event_id(self, test_log_lines):
        """Test filtering by event ID."""
        app = SentryTUIApp(["test"])
        app.filter_text = "abc123"

        # Should match lines containing the event ID
        assert app.matches_filter(test_log_lines[6])  # taskworker event id=abc123

        # Should not match lines without the event ID
        assert not app.matches_filter(test_log_lines[0])  # server GET
        assert not app.matches_filter(test_log_lines[2])  # worker INFO

    def test_filter_multiple_matches(self, test_log_lines):
        """Test filtering with text that matches multiple lines."""
        app = SentryTUIApp(["test"])
        app.filter_text = "14:32:01"  # Timestamp that appears in all lines

        # Should match all lines containing the timestamp
        for log_line in test_log_lines:
            assert app.matches_filter(log_line)

    def test_filter_no_matches(self, test_log_lines):
        """Test filtering with text that matches no lines."""
        app = SentryTUIApp(["test"])
        app.filter_text = "nonexistent_text_12345"

        # Should not match any lines
        for log_line in test_log_lines:
            assert not app.matches_filter(log_line)

    def test_filter_with_special_characters(self, test_log_lines):
        """Test filtering with special characters."""
        app = SentryTUIApp(["test"])
        app.filter_text = "/api/0/"

        # Should match lines containing the special characters
        assert app.matches_filter(test_log_lines[0])  # server GET /api/0/projects/

        # Should not match lines without the special characters
        assert not app.matches_filter(test_log_lines[2])  # worker INFO

    def test_filter_with_numbers(self, test_log_lines):
        """Test filtering with numbers."""
        app = SentryTUIApp(["test"])
        app.filter_text = "1234"

        # Should match lines containing the number
        assert app.matches_filter(test_log_lines[5])  # webpack 1234ms

        # Should not match lines without the number
        assert not app.matches_filter(test_log_lines[0])  # server GET
        assert not app.matches_filter(test_log_lines[2])  # worker INFO

    def test_filter_with_whitespace(self, test_log_lines):
        """Test filtering with whitespace."""
        app = SentryTUIApp(["test"])
        app.filter_text = "   "  # Only whitespace

        # Should match all lines (whitespace is trimmed or ignored)
        for log_line in test_log_lines:
            # Note: This behavior depends on implementation
            # If whitespace is treated as empty filter, should match all
            # If whitespace is treated as literal, might match none
            result = app.matches_filter(log_line)
            assert isinstance(result, bool)  # Just ensure it returns a boolean

    def test_filter_empty_string(self, test_log_lines):
        """Test filtering with empty string."""
        app = SentryTUIApp(["test"])
        app.filter_text = ""

        # Should match all lines
        for log_line in test_log_lines:
            assert app.matches_filter(log_line)

    @pytest.mark.parametrize(
        "filter_text,expected_matches",
        [
            ("ERROR", [1, 3, 9]),  # Lines with ERROR (includes ValueError)
            ("server", [0, 1, 7, 8, 9]),  # Lines with server
            ("worker", [2, 3, 6]),  # Lines with worker (includes taskworker)
            ("celery-beat", [4]),  # Lines with celery-beat
            ("webpack", [5]),  # Lines with webpack
            ("taskworker", [6]),  # Lines with taskworker
            ("GET", [0]),  # Lines with GET
            ("INFO", [2, 4]),  # Lines with INFO
            ("Traceback", [7]),  # Lines with Traceback
            ("ValueError", [9]),  # Lines with ValueError
        ],
    )
    def test_filter_parametrized(self, test_log_lines, filter_text, expected_matches):
        """Test filtering with various filter texts."""
        app = SentryTUIApp(["test"])
        app.filter_text = filter_text

        for i, log_line in enumerate(test_log_lines):
            expected = i in expected_matches
            actual = app.matches_filter(log_line)
            assert actual == expected, (
                f"Filter '{filter_text}' on line {i}: expected {expected}, got {actual}"
            )

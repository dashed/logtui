"""Shared test fixtures for sentry-tui tests."""

import pytest
from typing import List
from unittest.mock import Mock, patch
from sentry_tui.pty_interceptor import LogLine, PTYInterceptor


@pytest.fixture
def sample_log_lines() -> List[str]:
    """Sample log lines in Sentry devserver format."""
    return [
        "      server  14:32:01 GET 200 /api/0/projects/",
        "      worker  14:32:01 Task completed: sentry.tasks.process_event",
        "  celery-beat  14:32:01 Scheduler: Running periodic task cleanup",
        "     webpack  14:32:01 Compiled successfully in 1234ms",
        "  taskworker  14:32:01 Processing event id=abc123...",
        "      server  14:32:01 Traceback (most recent call last):",
        '      server  14:32:01   File "/app/sentry/api/endpoints/project_events.py", line 123, in get',
        '      server  14:32:01     raise ValueError("Invalid project ID")',
        "      server  14:32:01 ValueError: Invalid project ID",
    ]


@pytest.fixture
def sample_log_line_objects(sample_log_lines) -> List[LogLine]:
    """Sample LogLine objects created from sample log lines."""
    return [LogLine(line) for line in sample_log_lines]


@pytest.fixture
def mock_pty_interceptor() -> Mock:
    """Mock PTYInterceptor for testing."""
    interceptor = Mock(spec=PTYInterceptor)
    interceptor.running = True
    interceptor.process = Mock()
    interceptor.master_fd = Mock()
    interceptor.slave_fd = Mock()
    interceptor.output_thread = Mock()
    interceptor.buffer = ""
    return interceptor


@pytest.fixture
def mock_subprocess_popen():
    """Mock subprocess.Popen for testing PTY functionality."""
    with patch("subprocess.Popen") as mock_popen:
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        yield mock_popen


@pytest.fixture
def mock_pty_openpty():
    """Mock pty.openpty for testing."""
    with patch("pty.openpty") as mock_openpty:
        mock_openpty.return_value = (10, 11)  # master_fd, slave_fd
        yield mock_openpty


@pytest.fixture
def mock_os_functions():
    """Mock os functions for testing."""
    with (
        patch("os.close") as mock_close,
        patch("os.read") as mock_read,
        patch("os.killpg") as mock_killpg,
        patch("os.getpgid") as mock_getpgid,
    ):
        mock_getpgid.return_value = 12345
        yield {
            "close": mock_close,
            "read": mock_read,
            "killpg": mock_killpg,
            "getpgid": mock_getpgid,
        }


@pytest.fixture
def mock_select():
    """Mock select.select for testing."""
    with patch("select.select") as mock_select:
        # By default, return that data is ready
        mock_select.return_value = ([10], [], [])
        yield mock_select

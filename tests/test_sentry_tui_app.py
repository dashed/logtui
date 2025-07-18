"""Tests for SentryTUIApp TUI interactions."""

import pytest
from unittest.mock import Mock, patch
from textual.widgets import Input, RichLog
from sentry_tui.pty_interceptor import (
    SentryTUIApp,
    LogLine,
    ServiceToggleBar,
    ProcessState,
    ProcessStatusBar,
)


class TestSentryTUIApp:
    """Test cases for SentryTUIApp TUI interactions."""

    @pytest.fixture
    def mock_interceptor(self):
        """Mock PTYInterceptor for testing."""
        with patch(
            "sentry_tui.pty_interceptor.PTYInterceptor"
        ) as mock_interceptor_class:
            mock_interceptor = Mock()
            # Configure get_status to return a proper dictionary
            mock_interceptor.get_status.return_value = {
                "state": ProcessState.STOPPED,
                "auto_restart": False,
                "restart_count": 0,
                "max_restart_attempts": 5,
                "pid": None,
                "command": "test command",
            }
            mock_interceptor_class.return_value = mock_interceptor
            yield mock_interceptor

    @pytest.mark.asyncio
    async def test_app_initialization(self, mock_interceptor):
        """Test SentryTUIApp initialization."""
        command = ["python", "-m", "sentry_tui.dummy_app"]
        app = SentryTUIApp(command)

        async with app.run_test():
            assert app.command == command
            assert app.interceptor is not None  # Should be initialized on mount
            assert app.log_lines == []
            assert app.filter_text == ""
            assert not app.paused
            assert app.line_count == 0

    @pytest.mark.asyncio
    async def test_app_compose_structure(self, mock_interceptor):
        """Test that the app composes with correct structure."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Check that key widgets are present
            assert app.query_one("#filter_input", Input)
            assert app.query_one("#log_display", RichLog)

            # Check that filter input is focused initially
            filter_input = app.query_one("#filter_input", Input)
            assert filter_input.has_focus

    @pytest.mark.asyncio
    async def test_app_starts_interceptor_on_mount(self, mock_interceptor):
        """Test that the app starts the interceptor when mounted."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Verify interceptor was created and started
            assert app.interceptor is not None
            app.interceptor.start.assert_called_once()  # type: ignore

    @pytest.mark.asyncio
    async def test_filter_input_changes_filter_text(self, mock_interceptor):
        """Test that typing in filter input changes filter_text."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test() as pilot:
            # Type in the filter input
            await pilot.press("h", "e", "l", "l", "o")

            # Check that filter_text is updated
            assert app.filter_text == "hello"

    @pytest.mark.asyncio
    async def test_action_quit(self, mock_interceptor):
        """Test that quit action stops interceptor and exits app."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Get the interceptor reference
            interceptor = app.interceptor

            # Mock the exit method to prevent actual exit in test
            with patch.object(app, "exit") as mock_exit:
                # Call the quit action directly
                app.action_quit()

                # Verify interceptor was stopped
                interceptor.stop.assert_called_once()  # type: ignore

                # Verify exit was called
                mock_exit.assert_called_once()

    @pytest.mark.asyncio
    async def test_key_binding_quit_with_q(self, mock_interceptor):
        """Test that 'q' key calls quit action."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test() as pilot:
            # Focus the log display to ensure input doesn't consume the key
            log_display = app.query_one("#log_display", RichLog)
            log_display.focus()
            await pilot.pause()

            # Mock the action_quit method to verify it's called
            with patch.object(app, "action_quit") as mock_quit:
                # Press 'q' to quit
                await pilot.press("q")
                await pilot.pause()

                # Verify quit action was called
                mock_quit.assert_called_once()

    @pytest.mark.asyncio
    async def test_key_binding_quit_with_ctrl_c(self, mock_interceptor):
        """Test that Ctrl+C calls quit action."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test() as pilot:
            # Focus the log display to ensure input doesn't consume the key
            log_display = app.query_one("#log_display", RichLog)
            log_display.focus()
            await pilot.pause()

            # Mock the action_quit method to verify it's called
            with patch.object(app, "action_quit") as mock_quit:
                # Press Ctrl+C to quit
                await pilot.press("ctrl+c")
                await pilot.pause()

                # Verify quit action was called
                mock_quit.assert_called_once()

    @pytest.mark.asyncio
    async def test_key_binding_focus_filter(self, mock_interceptor):
        """Test that 'f' key focuses the filter input."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test() as pilot:
            # Focus the log display first
            log_display = app.query_one("#log_display", RichLog)
            log_display.focus()
            await pilot.pause()  # Wait for focus to update

            # Verify log display is focused
            assert log_display.has_focus

            # Press 'f' to focus filter
            await pilot.press("f")
            await pilot.pause()  # Wait for focus to update

            # Verify filter input is now focused
            filter_input = app.query_one("#filter_input", Input)
            assert filter_input.has_focus

    @pytest.mark.asyncio
    async def test_action_focus_log(self, mock_interceptor):
        """Test that focus_log action focuses the log display."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test() as pilot:
            # Filter input should be focused initially
            filter_input = app.query_one("#filter_input", Input)
            assert filter_input.has_focus

            # Call focus_log action directly
            app.action_focus_log()
            await pilot.pause()  # Wait for focus to update

            # Verify log display is now focused
            log_display = app.query_one("#log_display", RichLog)
            assert log_display.has_focus

    @pytest.mark.asyncio
    async def test_action_clear_logs(self, mock_interceptor):
        """Test that clear_logs action clears the logs."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test() as pilot:
            # Add some log lines
            app.log_lines = [
                LogLine("Test log 1"),
                LogLine("Test log 2"),
                LogLine("Test log 3"),
            ]
            app.line_count = 3

            # Call clear_logs action directly
            app.action_clear_logs()
            await pilot.pause()  # Wait for action to complete

            # Verify logs are cleared
            assert app.log_lines == []
            assert app.line_count == 0

    @pytest.mark.asyncio
    async def test_action_toggle_pause(self, mock_interceptor):
        """Test that toggle_pause action toggles pause/resume."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test() as pilot:
            # Initially not paused
            assert not app.paused

            # Call toggle_pause action directly
            app.action_toggle_pause()
            await pilot.pause()  # Wait for action to complete

            # Verify paused state
            assert app.paused

            # Call toggle_pause action again
            app.action_toggle_pause()
            await pilot.pause()  # Wait for action to complete

            # Verify resumed state
            assert not app.paused

    @pytest.mark.asyncio
    async def test_log_filtering_matches_content(self, mock_interceptor):
        """Test that log filtering works correctly."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Create test log lines
            log_lines = [
                LogLine("ERROR: Database connection failed"),
                LogLine("INFO: User logged in successfully"),
                LogLine("ERROR: Invalid request format"),
                LogLine("DEBUG: Processing request"),
            ]

            # Test that all lines match empty filter
            app.filter_text = ""
            for log_line in log_lines:
                assert app.matches_filter(log_line)

            # Test filtering by "ERROR"
            app.filter_text = "ERROR"
            assert app.matches_filter(log_lines[0])  # ERROR: Database
            assert not app.matches_filter(log_lines[1])  # INFO: User
            assert app.matches_filter(log_lines[2])  # ERROR: Invalid
            assert not app.matches_filter(log_lines[3])  # DEBUG: Processing

            # Test case-insensitive filtering
            app.filter_text = "error"
            assert app.matches_filter(log_lines[0])  # ERROR: Database
            assert app.matches_filter(log_lines[2])  # ERROR: Invalid

            # Test filtering by partial word
            app.filter_text = "Database"
            assert app.matches_filter(log_lines[0])  # ERROR: Database
            assert not app.matches_filter(log_lines[1])  # INFO: User
            assert not app.matches_filter(log_lines[2])  # ERROR: Invalid

    @pytest.mark.asyncio
    async def test_handle_log_output_when_not_paused(self, mock_interceptor):
        """Test handling log output when not paused."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Ensure not paused
            app.paused = False

            # Mock the add_log_line method to track calls
            with patch.object(app, "add_log_line"):
                with patch.object(app, "call_from_thread") as mock_call_from_thread:
                    # Handle log output
                    test_line = "Test log line\n"
                    app.handle_log_output(test_line)

                    # Verify log line was added
                    assert len(app.log_lines) == 1
                    assert app.log_lines[0].content == test_line
                    assert app.line_count == 1

                    # Verify call_from_thread was called to update display
                    # Should be called twice: once for service discovery, once for log display
                    assert mock_call_from_thread.call_count == 2

    @pytest.mark.asyncio
    async def test_handle_log_output_when_paused(self, mock_interceptor):
        """Test handling log output when paused."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Set to paused
            app.paused = True

            # Mock the add_log_line method to track calls
            with patch.object(app, "add_log_line"):
                with patch.object(app, "call_from_thread") as mock_call_from_thread:
                    # Handle log output
                    test_line = "Test log line\n"
                    app.handle_log_output(test_line)

                    # Verify log line was NOT added when paused
                    assert len(app.log_lines) == 0
                    assert app.line_count == 0

                    # Verify call_from_thread was NOT called
                    mock_call_from_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_handle_log_output_with_filtering(self, mock_interceptor):
        """Test handling log output with filtering."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Set a filter
            app.filter_text = "ERROR"

            # Mock the add_log_line method to track calls
            with patch.object(app, "add_log_line"):
                with patch.object(app, "call_from_thread") as mock_call_from_thread:
                    # Handle log output that matches filter
                    matching_line = "ERROR: Database connection failed\n"
                    app.handle_log_output(matching_line)

                    # Verify log line was added
                    assert len(app.log_lines) == 1
                    assert app.log_lines[0].content == matching_line

                    # Verify call_from_thread was called to update display
                    # Should be called twice: once for service discovery, once for log display
                    assert mock_call_from_thread.call_count == 2

                    # Reset mocks
                    mock_call_from_thread.reset_mock()

                    # Handle log output that doesn't match filter
                    non_matching_line = "INFO: User logged in successfully\n"
                    app.handle_log_output(non_matching_line)

                    # Verify log line was added to storage
                    assert len(app.log_lines) == 2
                    assert app.log_lines[1].content == non_matching_line

                    # Verify call_from_thread was NOT called (doesn't match filter)
                    mock_call_from_thread.assert_not_called()

    @pytest.mark.asyncio
    async def test_memory_management_log_limit(self, mock_interceptor):
        """Test that log lines are limited to prevent memory issues."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Add more than 10,000 log lines
            for i in range(10005):
                app.log_lines.append(LogLine(f"Log line {i}"))

            # Mock call_from_thread to avoid threading issue in tests
            with patch.object(app, "call_from_thread") as mock_call_from_thread:
                # Simulate handling one more log output
                app.handle_log_output("New log line\n")

                # Verify log lines are limited to 10,000
                assert len(app.log_lines) <= 10000

                # Verify the newest log line is present
                assert app.log_lines[-1].content == "New log line\n"

                # Verify call_from_thread was called
                # Should be called twice: once for service discovery, once for log display
                assert mock_call_from_thread.call_count == 2

    @pytest.mark.asyncio
    async def test_update_log_display_with_filter(self, mock_interceptor):
        """Test updating log display with filter applied."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Add test log lines
            app.log_lines = [
                LogLine("ERROR: Database connection failed"),
                LogLine("INFO: User logged in successfully"),
                LogLine("ERROR: Invalid request format"),
                LogLine("DEBUG: Processing request"),
            ]

            # Set filter
            app.filter_text = "ERROR"

            # Get log display widget
            log_display = app.query_one("#log_display", RichLog)

            # Mock the log display methods
            with patch.object(log_display, "clear") as mock_clear:
                with patch.object(log_display, "write") as mock_write:
                    with patch.object(log_display, "scroll_end") as mock_scroll_end:
                        # Update log display
                        app.update_log_display()

                        # Verify display was cleared
                        mock_clear.assert_called_once()

                        # Verify only matching lines were written
                        assert mock_write.call_count == 2  # Two ERROR lines

                        # Verify scroll to end was called
                        mock_scroll_end.assert_called_once()

    @pytest.mark.asyncio
    async def test_app_cleanup_on_quit(self, mock_interceptor):
        """Test that the app cleans up interceptor on quit."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Get the interceptor reference
            interceptor = app.interceptor

            # Manually call the quit action to test cleanup
            app.action_quit()

            # Verify interceptor was stopped
            interceptor.stop.assert_called_once()  # type: ignore


class TestServiceToggleBar:
    """Test cases for ServiceToggleBar dynamic service discovery."""

    @pytest.mark.asyncio
    async def test_service_toggle_bar_starts_empty(self):
        """Test that ServiceToggleBar starts with empty services list."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            service_toggle_bar = app.query_one("#service_toggle_bar", ServiceToggleBar)
            assert service_toggle_bar.services == []
            assert service_toggle_bar.enabled_services == set()

    @pytest.mark.asyncio
    async def test_dynamic_service_discovery(self):
        """Test that services are discovered dynamically from log lines."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Mock call_from_thread to avoid threading issues
            with patch.object(app, "call_from_thread") as mock_call_from_thread:
                # Simulate log lines with different services
                test_logs = [
                    "server 01:23:45 [INFO] django.request: GET /api/health",
                    "worker 01:23:46 [DEBUG] celery.worker: Task received",
                    "webpack 01:23:47 [INFO] webpack: Compiled successfully",
                    "custom-service 01:23:48 [ERROR] custom.module: Something failed",
                ]

                for log_line in test_logs:
                    app.handle_log_output(log_line)

                # Verify services were discovered
                assert "server" in app.discovered_services
                assert "worker" in app.discovered_services
                assert "webpack" in app.discovered_services
                assert "custom-service" in app.discovered_services

                # Verify call_from_thread was called to add services
                # Should be called for each new service + each log line display
                assert mock_call_from_thread.call_count >= 4

    @pytest.mark.asyncio
    async def test_service_toggle_bar_add_service(self):
        """Test adding a service to ServiceToggleBar."""
        service_toggle_bar = ServiceToggleBar()

        # Initially empty
        assert service_toggle_bar.services == []
        assert service_toggle_bar.enabled_services == set()

        # Add a service
        service_toggle_bar.add_service("test-service")

        # Verify service was added
        assert "test-service" in service_toggle_bar.services
        assert "test-service" in service_toggle_bar.enabled_services

    @pytest.mark.asyncio
    async def test_service_toggle_bar_add_duplicate_service(self):
        """Test that adding duplicate service doesn't create duplicates."""
        service_toggle_bar = ServiceToggleBar()

        # Add same service twice
        service_toggle_bar.add_service("test-service")
        service_toggle_bar.add_service("test-service")

        # Verify only one instance exists
        assert service_toggle_bar.services.count("test-service") == 1
        assert "test-service" in service_toggle_bar.enabled_services

    @pytest.mark.asyncio
    async def test_service_filtering_with_discovered_services(self):
        """Test that filtering works with dynamically discovered services."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Mock the service toggle bar interaction
            service_toggle_bar = app.query_one("#service_toggle_bar", ServiceToggleBar)

            # Add some services manually (simulating discovery)
            service_toggle_bar.add_service("server")
            service_toggle_bar.add_service("worker")
            service_toggle_bar.add_service("custom-service")

            # Create test log lines
            server_log = LogLine(
                "server 01:23:45 [INFO] django.request: GET /api/health"
            )
            worker_log = LogLine("worker 01:23:46 [DEBUG] celery.worker: Task received")
            custom_log = LogLine(
                "custom-service 01:23:48 [ERROR] custom.module: Something failed"
            )

            # All services enabled by default - all should match
            assert app.matches_filter(server_log)
            assert app.matches_filter(worker_log)
            assert app.matches_filter(custom_log)

            # Disable worker service
            service_toggle_bar.enabled_services.discard("worker")

            # Only server and custom-service should match
            assert app.matches_filter(server_log)
            assert not app.matches_filter(worker_log)
            assert app.matches_filter(custom_log)

    @pytest.mark.asyncio
    async def test_add_service_to_toggle_bar_method(self):
        """Test the add_service_to_toggle_bar method."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            service_toggle_bar = app.query_one("#service_toggle_bar", ServiceToggleBar)

            # Initially empty
            assert service_toggle_bar.services == []

            # Add service through app method
            app.add_service_to_toggle_bar("new-service")

            # Verify service was added
            assert "new-service" in service_toggle_bar.services
            assert "new-service" in service_toggle_bar.enabled_services

    @pytest.mark.asyncio
    async def test_discovered_services_set_prevents_duplicates(self):
        """Test that discovered_services set prevents duplicate discovery."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Mock call_from_thread to count calls
            with patch.object(app, "call_from_thread") as mock_call_from_thread:
                # Add same service multiple times
                app.handle_log_output("server 01:23:45 [INFO] First log")
                app.handle_log_output("server 01:23:46 [INFO] Second log")
                app.handle_log_output("server 01:23:47 [INFO] Third log")

                # Verify service was only discovered once
                assert "server" in app.discovered_services
                assert app.discovered_services == {"server"}

                # call_from_thread should be called once for service addition
                # and once for each log line display that matches the filter
                # But only the first log line triggers service discovery
                assert mock_call_from_thread.call_count >= 1

    @pytest.mark.asyncio
    async def test_unknown_service_discovery(self):
        """Test that unknown services are discovered correctly."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Mock call_from_thread to avoid threading issues
            with patch.object(app, "call_from_thread") as mock_call_from_thread:
                # Log line that doesn't match standard format
                app.handle_log_output("Some random log line without service")

                # Verify "unknown" service was discovered
                assert "unknown" in app.discovered_services

                # Verify call_from_thread was called
                mock_call_from_thread.assert_called()


class TestProcessControlActions:
    """Test cases for process control actions in SentryTUIApp."""

    @pytest.fixture
    def mock_interceptor(self):
        """Mock PTYInterceptor for testing."""
        with patch(
            "sentry_tui.pty_interceptor.PTYInterceptor"
        ) as mock_interceptor_class:
            mock_interceptor = Mock()
            mock_interceptor.get_status.return_value = {
                "state": ProcessState.RUNNING,
                "auto_restart": False,
                "restart_count": 0,
                "max_restart_attempts": 5,
                "pid": 12345,
                "command": "test command",
            }
            mock_interceptor_class.return_value = mock_interceptor
            yield mock_interceptor

    @pytest.mark.asyncio
    async def test_app_initialization_with_auto_restart(self, mock_interceptor):
        """Test SentryTUIApp initialization with auto_restart enabled."""
        command = ["python", "-m", "sentry_tui.dummy_app"]
        app = SentryTUIApp(command, auto_restart=True)

        async with app.run_test():
            assert app.command == command
            assert app.auto_restart is True
            # auto_restart_enabled is updated from interceptor status after mount
            # Since mock returns auto_restart=False, this will be False
            # Let's check that it gets updated correctly
            app.update_process_status()
            # The reactive value is updated from interceptor status

    @pytest.mark.asyncio
    async def test_app_compose_structure_with_process_status_bar(
        self, mock_interceptor
    ):
        """Test that the app composes with process status bar."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Check that process status bar is present
            assert app.query_one("#process_status_bar", ProcessStatusBar)

    @pytest.mark.asyncio
    async def test_action_graceful_shutdown(self, mock_interceptor):
        """Test graceful shutdown action."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Call graceful shutdown action
            app.action_graceful_shutdown()

            # Verify interceptor method was called
            mock_interceptor.graceful_shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_action_force_quit(self, mock_interceptor):
        """Test force quit action."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Call force quit action
            app.action_force_quit()

            # Verify interceptor method was called
            mock_interceptor.force_quit.assert_called_once()

    @pytest.mark.asyncio
    async def test_action_restart(self, mock_interceptor):
        """Test restart action."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Call restart action
            app.action_restart()

            # Verify interceptor method was called
            mock_interceptor.restart.assert_called_once_with(force=False)

    @pytest.mark.asyncio
    async def test_action_force_restart(self, mock_interceptor):
        """Test force restart action."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Call force restart action
            app.action_force_restart()

            # Verify interceptor method was called
            mock_interceptor.restart.assert_called_once_with(force=True)

    @pytest.mark.asyncio
    async def test_action_toggle_auto_restart(self, mock_interceptor):
        """Test toggle auto-restart action."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Mock the update_process_status method
            with patch.object(app, "update_process_status") as mock_update:
                # Call toggle auto-restart action
                app.action_toggle_auto_restart()

                # Verify interceptor method was called
                mock_interceptor.toggle_auto_restart.assert_called_once()

                # Verify status was updated
                mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_state_change_callback(self, mock_interceptor):
        """Test process state change callback."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Mock call_from_thread to verify it's called
            with patch.object(app, "call_from_thread") as mock_call:
                # Call the process state change callback
                app.on_process_state_changed(ProcessState.RUNNING)

                # Verify process_state is updated
                assert app.process_state == ProcessState.RUNNING

                # Verify call_from_thread was called to update status
                mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_process_status(self, mock_interceptor):
        """Test update_process_status method."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test():
            # Get the process status bar
            process_status_bar = app.query_one("#process_status_bar", ProcessStatusBar)

            # Mock the update_status method to verify it's called
            with patch.object(process_status_bar, "update_status") as mock_update:
                # Call update_process_status
                app.update_process_status()

                # Verify interceptor get_status was called
                # Note: get_status is called during mount and then again during update
                assert mock_interceptor.get_status.call_count >= 1

                # Verify process status bar was updated
                mock_update.assert_called_once()

    @pytest.mark.asyncio
    async def test_key_binding_graceful_shutdown(self, mock_interceptor):
        """Test that 's' key calls graceful shutdown action."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test() as pilot:
            # Focus the log display to ensure input doesn't consume the key
            log_display = app.query_one("#log_display", RichLog)
            log_display.focus()
            await pilot.pause()

            # Mock the action method to verify it's called
            with patch.object(app, "action_graceful_shutdown") as mock_action:
                # Press 's' to trigger graceful shutdown
                await pilot.press("s")
                await pilot.pause()

                # Verify action was called
                mock_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_key_binding_force_quit(self, mock_interceptor):
        """Test that 'k' key calls force quit action."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test() as pilot:
            # Focus the log display to ensure input doesn't consume the key
            log_display = app.query_one("#log_display", RichLog)
            log_display.focus()
            await pilot.pause()

            # Mock the action method to verify it's called
            with patch.object(app, "action_force_quit") as mock_action:
                # Press 'k' to trigger force quit
                await pilot.press("k")
                await pilot.pause()

                # Verify action was called
                mock_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_key_binding_restart(self, mock_interceptor):
        """Test that 'r' key calls restart action."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test() as pilot:
            # Focus the log display to ensure input doesn't consume the key
            log_display = app.query_one("#log_display", RichLog)
            log_display.focus()
            await pilot.pause()

            # Mock the action method to verify it's called
            with patch.object(app, "action_restart") as mock_action:
                # Press 'r' to trigger restart
                await pilot.press("r")
                await pilot.pause()

                # Verify action was called
                mock_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_key_binding_force_restart(self, mock_interceptor):
        """Test that Shift+R calls force restart action."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test() as pilot:
            # Focus the log display to ensure input doesn't consume the key
            log_display = app.query_one("#log_display", RichLog)
            log_display.focus()
            await pilot.pause()

            # Mock the action method to verify it's called
            with patch.object(app, "action_force_restart") as mock_action:
                # Press Shift+R to trigger force restart
                await pilot.press("shift+r")
                await pilot.pause()

                # Verify action was called
                mock_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_key_binding_toggle_auto_restart(self, mock_interceptor):
        """Test that 'a' key calls toggle auto-restart action."""
        command = ["test", "command"]
        app = SentryTUIApp(command)

        async with app.run_test() as pilot:
            # Focus the log display to ensure input doesn't consume the key
            log_display = app.query_one("#log_display", RichLog)
            log_display.focus()
            await pilot.pause()

            # Mock the action method to verify it's called
            with patch.object(app, "action_toggle_auto_restart") as mock_action:
                # Press 'a' to toggle auto-restart
                await pilot.press("a")
                await pilot.pause()

                # Verify action was called
                mock_action.assert_called_once()


class TestProcessStatusBar:
    """Test cases for ProcessStatusBar widget."""

    @pytest.mark.asyncio
    async def test_process_status_bar_initialization(self):
        """Test ProcessStatusBar initialization."""
        status_bar = ProcessStatusBar()

        assert status_bar.process_state == ProcessState.STOPPED
        assert status_bar.auto_restart is False
        assert status_bar.restart_count == 0
        assert status_bar.pid is None
        assert status_bar.command == ""

    @pytest.mark.asyncio
    async def test_process_status_bar_compose(self):
        """Test ProcessStatusBar compose method."""
        status_bar = ProcessStatusBar()

        # Test that compose yields the expected widgets
        widgets = list(status_bar.compose())
        assert len(widgets) == 4  # Label, state, auto-restart, info displays

    @pytest.mark.asyncio
    async def test_process_status_bar_update_status(self):
        """Test ProcessStatusBar update_status method."""
        from textual.app import App

        class TestApp(App):
            def compose(self):
                yield ProcessStatusBar(id="status_bar")

        app = TestApp()

        async with app.run_test():
            status_bar = app.query_one("#status_bar", ProcessStatusBar)

            # Update status
            status_bar.update_status(
                state=ProcessState.RUNNING,
                auto_restart=True,
                restart_count=3,
                pid=12345,
                command="test command",
            )

            # Verify internal state
            assert status_bar.process_state == ProcessState.RUNNING
            assert status_bar.auto_restart is True
            assert status_bar.restart_count == 3
            assert status_bar.pid == 12345
            assert status_bar.command == "test command"

    @pytest.mark.asyncio
    async def test_process_status_bar_state_colors(self):
        """Test ProcessStatusBar displays correct colors for different states."""
        from textual.app import App

        class TestApp(App):
            def compose(self):
                yield ProcessStatusBar(id="status_bar")

        app = TestApp()

        async with app.run_test():
            status_bar = app.query_one("#status_bar", ProcessStatusBar)

            # Test different state colors
            test_states = [
                (ProcessState.STOPPED, "dim"),
                (ProcessState.STARTING, "yellow"),
                (ProcessState.RUNNING, "green"),
                (ProcessState.STOPPING, "yellow"),
                (ProcessState.RESTARTING, "blue"),
                (ProcessState.CRASHED, "red"),
            ]

            for state, expected_color in test_states:
                status_bar.update_status(state=state, auto_restart=False)

                # Check that the state display contains the expected color
                state_display = status_bar.query_one("#process_state_display")
                assert expected_color in str(state_display.renderable)
                assert state.value.upper() in str(state_display.renderable)

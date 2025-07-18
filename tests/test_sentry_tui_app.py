"""Tests for SentryTUIApp TUI interactions."""

import pytest
from unittest.mock import Mock, patch, MagicMock
from textual.widgets import Input, RichLog
from sentry_tui.pty_interceptor import SentryTUIApp, LogLine


class TestSentryTUIApp:
    """Test cases for SentryTUIApp TUI interactions."""

    @pytest.fixture
    def mock_interceptor(self):
        """Mock PTYInterceptor for testing."""
        with patch('sentry_tui.pty_interceptor.PTYInterceptor') as mock_interceptor_class:
            mock_interceptor = Mock()
            mock_interceptor_class.return_value = mock_interceptor
            yield mock_interceptor

    @pytest.mark.asyncio
    async def test_app_initialization(self, mock_interceptor):
        """Test SentryTUIApp initialization."""
        command = ["python", "-m", "sentry_tui.dummy_app"]
        app = SentryTUIApp(command)
        
        assert app.command == command
        assert app.interceptor is None
        assert app.log_lines == []
        assert app.filter_text == ""
        assert app.paused == False
        assert app.line_count == 0

    @pytest.mark.asyncio
    async def test_app_compose_structure(self, mock_interceptor):
        """Test that the app composes with correct structure."""
        command = ["test", "command"]
        app = SentryTUIApp(command)
        
        async with app.run_test() as pilot:
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
        
        async with app.run_test() as pilot:
            # Verify interceptor was created and started
            assert app.interceptor is not None
            app.interceptor.start.assert_called_once()

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
    async def test_key_binding_quit_with_q(self, mock_interceptor):
        """Test that 'q' key quits the application."""
        command = ["test", "command"]
        app = SentryTUIApp(command)
        
        async with app.run_test() as pilot:
            # Press 'q' to quit
            await pilot.press("q")
            
            # App should have exited
            assert not app.is_running

    @pytest.mark.asyncio
    async def test_key_binding_quit_with_ctrl_c(self, mock_interceptor):
        """Test that Ctrl+C quits the application."""
        command = ["test", "command"]
        app = SentryTUIApp(command)
        
        async with app.run_test() as pilot:
            # Press Ctrl+C to quit
            await pilot.press("ctrl+c")
            
            # App should have exited
            assert not app.is_running

    @pytest.mark.asyncio
    async def test_key_binding_focus_filter(self, mock_interceptor):
        """Test that 'f' key focuses the filter input."""
        command = ["test", "command"]
        app = SentryTUIApp(command)
        
        async with app.run_test() as pilot:
            # Focus the log display first
            log_display = app.query_one("#log_display", RichLog)
            log_display.focus()
            
            # Verify filter input is not focused
            filter_input = app.query_one("#filter_input", Input)
            assert not filter_input.has_focus
            
            # Press 'f' to focus filter
            await pilot.press("f")
            
            # Verify filter input is now focused
            assert filter_input.has_focus

    @pytest.mark.asyncio
    async def test_key_binding_focus_log(self, mock_interceptor):
        """Test that 'l' key focuses the log display."""
        command = ["test", "command"]
        app = SentryTUIApp(command)
        
        async with app.run_test() as pilot:
            # Filter input should be focused initially
            filter_input = app.query_one("#filter_input", Input)
            assert filter_input.has_focus
            
            # Press 'l' to focus log display
            await pilot.press("l")
            
            # Verify log display is now focused
            log_display = app.query_one("#log_display", RichLog)
            assert log_display.has_focus

    @pytest.mark.asyncio
    async def test_key_binding_clear_logs(self, mock_interceptor):
        """Test that 'c' key clears the logs."""
        command = ["test", "command"]
        app = SentryTUIApp(command)
        
        async with app.run_test() as pilot:
            # Add some log lines
            app.log_lines = [
                LogLine("Test log 1"),
                LogLine("Test log 2"),
                LogLine("Test log 3")
            ]
            app.line_count = 3
            
            # Press 'c' to clear logs
            await pilot.press("c")
            
            # Verify logs are cleared
            assert app.log_lines == []
            assert app.line_count == 0

    @pytest.mark.asyncio
    async def test_key_binding_toggle_pause(self, mock_interceptor):
        """Test that 'p' key toggles pause/resume."""
        command = ["test", "command"]
        app = SentryTUIApp(command)
        
        async with app.run_test() as pilot:
            # Initially not paused
            assert app.paused == False
            
            # Press 'p' to pause
            await pilot.press("p")
            
            # Verify paused state
            assert app.paused == True
            
            # Press 'p' again to resume
            await pilot.press("p")
            
            # Verify resumed state
            assert app.paused == False

    @pytest.mark.asyncio
    async def test_log_filtering_matches_content(self, mock_interceptor):
        """Test that log filtering works correctly."""
        command = ["test", "command"]
        app = SentryTUIApp(command)
        
        async with app.run_test() as pilot:
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
                assert app.matches_filter(log_line) == True
            
            # Test filtering by "ERROR"
            app.filter_text = "ERROR"
            assert app.matches_filter(log_lines[0]) == True  # ERROR: Database
            assert app.matches_filter(log_lines[1]) == False  # INFO: User
            assert app.matches_filter(log_lines[2]) == True  # ERROR: Invalid
            assert app.matches_filter(log_lines[3]) == False  # DEBUG: Processing
            
            # Test case-insensitive filtering
            app.filter_text = "error"
            assert app.matches_filter(log_lines[0]) == True  # ERROR: Database
            assert app.matches_filter(log_lines[2]) == True  # ERROR: Invalid
            
            # Test filtering by partial word
            app.filter_text = "Database"
            assert app.matches_filter(log_lines[0]) == True  # ERROR: Database
            assert app.matches_filter(log_lines[1]) == False  # INFO: User
            assert app.matches_filter(log_lines[2]) == False  # ERROR: Invalid

    @pytest.mark.asyncio
    async def test_handle_log_output_when_not_paused(self, mock_interceptor):
        """Test handling log output when not paused."""
        command = ["test", "command"]
        app = SentryTUIApp(command)
        
        async with app.run_test() as pilot:
            # Ensure not paused
            app.paused = False
            
            # Mock the add_log_line method to track calls
            with patch.object(app, 'add_log_line') as mock_add_log:
                with patch.object(app, 'call_from_thread') as mock_call_from_thread:
                    # Handle log output
                    test_line = "Test log line\n"
                    app.handle_log_output(test_line)
                    
                    # Verify log line was added
                    assert len(app.log_lines) == 1
                    assert app.log_lines[0].content == test_line
                    assert app.line_count == 1
                    
                    # Verify call_from_thread was called to update display
                    mock_call_from_thread.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_log_output_when_paused(self, mock_interceptor):
        """Test handling log output when paused."""
        command = ["test", "command"]
        app = SentryTUIApp(command)
        
        async with app.run_test() as pilot:
            # Set to paused
            app.paused = True
            
            # Mock the add_log_line method to track calls
            with patch.object(app, 'add_log_line') as mock_add_log:
                with patch.object(app, 'call_from_thread') as mock_call_from_thread:
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
        
        async with app.run_test() as pilot:
            # Set a filter
            app.filter_text = "ERROR"
            
            # Mock the add_log_line method to track calls
            with patch.object(app, 'add_log_line') as mock_add_log:
                with patch.object(app, 'call_from_thread') as mock_call_from_thread:
                    # Handle log output that matches filter
                    matching_line = "ERROR: Database connection failed\n"
                    app.handle_log_output(matching_line)
                    
                    # Verify log line was added
                    assert len(app.log_lines) == 1
                    assert app.log_lines[0].content == matching_line
                    
                    # Verify call_from_thread was called to update display
                    mock_call_from_thread.assert_called_once()
                    
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
        
        async with app.run_test() as pilot:
            # Add more than 10,000 log lines
            for i in range(10005):
                app.log_lines.append(LogLine(f"Log line {i}"))
            
            # Simulate handling one more log output
            app.handle_log_output("New log line\n")
            
            # Verify log lines are limited to 10,000
            assert len(app.log_lines) <= 10000
            
            # Verify the newest log line is present
            assert app.log_lines[-1].content == "New log line\n"

    @pytest.mark.asyncio
    async def test_update_log_display_with_filter(self, mock_interceptor):
        """Test updating log display with filter applied."""
        command = ["test", "command"]
        app = SentryTUIApp(command)
        
        async with app.run_test() as pilot:
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
            with patch.object(log_display, 'clear') as mock_clear:
                with patch.object(log_display, 'write') as mock_write:
                    with patch.object(log_display, 'scroll_end') as mock_scroll_end:
                        # Update log display
                        app.update_log_display()
                        
                        # Verify display was cleared
                        mock_clear.assert_called_once()
                        
                        # Verify only matching lines were written
                        assert mock_write.call_count == 2  # Two ERROR lines
                        
                        # Verify scroll to end was called
                        mock_scroll_end.assert_called_once()

    @pytest.mark.asyncio
    async def test_app_cleanup_on_unmount(self, mock_interceptor):
        """Test that the app cleans up interceptor on unmount."""
        command = ["test", "command"]
        app = SentryTUIApp(command)
        
        async with app.run_test() as pilot:
            # Get the interceptor reference
            interceptor = app.interceptor
            
            # Exit the app
            await pilot.press("q")
            
            # Verify interceptor was stopped
            interceptor.stop.assert_called_once()
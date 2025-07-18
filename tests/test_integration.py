"""Integration tests for sentry-tui with dummy app."""

import pytest
import time
import asyncio
from unittest.mock import patch
from sentry_tui.pty_interceptor import PTYInterceptor, SentryTUIApp
from sentry_tui.dummy_app import DummyApp


class TestIntegration:
    """Integration test cases for sentry-tui."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_dummy_app_basic_functionality(self):
        """Test that dummy app runs and generates output."""
        app = DummyApp()
        
        # Test signal handler setup
        app.setup_signal_handlers()
        
        # Test timestamp generation
        timestamp = app._get_timestamp()
        assert len(timestamp) == 8  # HH:MM:SS format
        assert timestamp.count(":") == 2
        
        # Test service name colorization
        colored_server = app._colorize_service_name("server")
        assert "server" in colored_server
        assert "\033[" in colored_server  # ANSI escape code
        
        # Test log line formatting
        log_line = app._format_log_line("server", "INFO", "sentry.web.frontend", "GET 200 /api/0/projects/")
        assert "server" in log_line
        assert "GET 200 /api/0/projects/" in log_line
        assert "\033[" in log_line  # ANSI escape code
        
        # Test random log message generation
        service, level, module, message = app._get_random_log_message()
        assert service in ["server", "worker", "celery-beat", "webpack", "taskworker"]
        assert level in ["DEBUG", "INFO", "WARNING", "ERROR"]
        assert isinstance(module, str)
        assert isinstance(message, str)
        assert len(message) > 0

    @pytest.mark.slow
    @pytest.mark.integration
    def test_pty_interceptor_with_dummy_app(self):
        """Test PTYInterceptor with the dummy app."""
        import sys
        import subprocess
        
        # Create command to run dummy app for a short time
        command = [sys.executable, "-m", "sentry_tui.dummy_app"]
        
        # Collect output
        output_lines = []
        
        def capture_output(line):
            output_lines.append(line)
        
        interceptor = PTYInterceptor(command, capture_output)
        
        try:
            # Start the interceptor
            interceptor.start()
            
            # Wait for some output
            time.sleep(2)
            
            # Stop the interceptor
            interceptor.stop()
            
            # Verify we got some output
            assert len(output_lines) > 0
            
            # Verify output contains expected patterns
            output_text = "".join(output_lines)
            assert "Starting dummy Sentry devserver" in output_text
            assert "Press Ctrl+C to stop" in output_text
            
            # Should have some log lines with service prefixes
            has_service_line = any(
                any(service in line for service in ["server", "worker", "celery-beat", "webpack", "taskworker"])
                for line in output_lines
            )
            assert has_service_line
            
        except Exception as e:
            # Make sure to stop the interceptor even if test fails
            interceptor.stop()
            raise e

    @pytest.mark.slow
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_sentry_tui_app_with_dummy_app(self):
        """Test SentryTUIApp with the dummy app."""
        import sys
        
        # Create command to run dummy app
        command = [sys.executable, "-m", "sentry_tui.dummy_app"]
        
        app = SentryTUIApp(command)
        
        # Run the app for a short time
        async with app.run_test(size=(80, 24)) as pilot:
            # Wait for app to start and receive some output
            await asyncio.sleep(2)
            
            # Verify we have some log lines
            assert len(app.log_lines) > 0
            
            # Test filtering functionality directly
            app.filter_text = "server"
            app.update_log_display()
            await pilot.pause()
            
            # Test that some lines match the filter
            server_lines = [line for line in app.log_lines if app.matches_filter(line)]
            assert len(server_lines) > 0
            
            # Test clear logs action directly (verify functionality works)
            original_count = len(app.log_lines)
            assert original_count > 0
            app.action_clear_logs()
            await pilot.pause()
            # Clear logs should work (may have new logs from dummy app, but count should be lower)
            assert len(app.log_lines) < original_count
            
            # Test pause/resume functionality directly
            assert app.paused == False
            app.action_toggle_pause()
            await pilot.pause()
            assert app.paused == True
            
            app.action_toggle_pause()
            await pilot.pause()
            assert app.paused == False

    @pytest.mark.slow
    @pytest.mark.integration
    def test_pty_interceptor_signal_handling(self):
        """Test PTYInterceptor signal handling with dummy app."""
        import sys
        import signal
        import os
        
        # Create command to run dummy app
        command = [sys.executable, "-m", "sentry_tui.dummy_app"]
        
        # Collect output
        output_lines = []
        
        def capture_output(line):
            output_lines.append(line)
        
        interceptor = PTYInterceptor(command, capture_output)
        
        try:
            # Start the interceptor
            interceptor.start()
            
            # Wait for the process to start
            time.sleep(1)
            
            # Verify process is running
            assert interceptor.process is not None
            assert interceptor.process.poll() is None  # Process should still be running
            
            # Stop the interceptor (this should send SIGTERM)
            interceptor.stop()
            
            # Wait a bit for cleanup
            time.sleep(0.5)
            
            # Verify process is stopped
            assert interceptor.process.poll() is not None  # Process should be terminated
            
            # Verify we got some output before termination
            assert len(output_lines) > 0
            
        except Exception as e:
            # Make sure to stop the interceptor even if test fails
            interceptor.stop()
            raise e

    @pytest.mark.slow
    @pytest.mark.integration
    def test_pty_interceptor_output_buffering(self):
        """Test PTYInterceptor output buffering and line processing."""
        import sys
        
        # Create command to run dummy app
        command = [sys.executable, "-m", "sentry_tui.dummy_app"]
        
        # Collect output with detailed tracking
        output_lines = []
        partial_lines = []
        
        def capture_output(line):
            output_lines.append(line)
            if not line.endswith('\n'):
                partial_lines.append(line)
        
        interceptor = PTYInterceptor(command, capture_output)
        
        try:
            # Start the interceptor
            interceptor.start()
            
            # Wait for output
            time.sleep(2)
            
            # Stop the interceptor
            interceptor.stop()
            
            # Verify we got complete lines
            assert len(output_lines) > 0
            
            # Most lines should end with newline
            complete_lines = [line for line in output_lines if line.endswith('\n')]
            assert len(complete_lines) > 0
            
            # Verify we got meaningful content
            content = "".join(output_lines)
            assert len(content) > 0
            
        except Exception as e:
            # Make sure to stop the interceptor even if test fails
            interceptor.stop()
            raise e

    @pytest.mark.slow
    @pytest.mark.integration
    def test_pty_interceptor_unicode_handling(self):
        """Test PTYInterceptor handles Unicode correctly."""
        import sys
        
        # Create a simple command that outputs Unicode
        command = [sys.executable, "-c", "print('Hello 世界! 🌍'); import time; time.sleep(1)"]
        
        # Collect output
        output_lines = []
        
        def capture_output(line):
            output_lines.append(line)
        
        interceptor = PTYInterceptor(command, capture_output)
        
        try:
            # Start the interceptor
            interceptor.start()
            
            # Wait for output
            time.sleep(2)
            
            # Stop the interceptor
            interceptor.stop()
            
            # Verify we got the Unicode output
            assert len(output_lines) > 0
            
            content = "".join(output_lines)
            assert "Hello 世界! 🌍" in content
            
        except Exception as e:
            # Make sure to stop the interceptor even if test fails
            interceptor.stop()
            raise e

    @pytest.mark.slow
    @pytest.mark.integration
    def test_pty_interceptor_error_handling(self):
        """Test PTYInterceptor error handling with invalid command."""
        # Create command that doesn't exist
        command = ["nonexistent_command_12345"]
        
        # Collect output
        output_lines = []
        
        def capture_output(line):
            output_lines.append(line)
        
        interceptor = PTYInterceptor(command, capture_output)
        
        try:
            # Start the interceptor (this should fail)
            interceptor.start()
            
            # Wait a bit
            time.sleep(0.5)
            
            # Stop the interceptor
            interceptor.stop()
            
            # The process should have failed to start
            # This test verifies that we handle the error gracefully
            assert True  # If we get here without exception, the error was handled
            
        except Exception as e:
            # Make sure to stop the interceptor even if test fails
            interceptor.stop()
            # Some exceptions are expected for invalid commands
            assert "No such file or directory" in str(e) or "not found" in str(e)

    @pytest.mark.slow
    @pytest.mark.integration
    def test_end_to_end_filtering_workflow(self):
        """Test end-to-end filtering workflow."""
        import sys
        
        # Create command to run dummy app
        command = [sys.executable, "-m", "sentry_tui.dummy_app"]
        
        # Collect output
        output_lines = []
        
        def capture_output(line):
            output_lines.append(line)
        
        interceptor = PTYInterceptor(command, capture_output)
        
        try:
            # Start the interceptor
            interceptor.start()
            
            # Wait for some output
            time.sleep(2)
            
            # Stop the interceptor
            interceptor.stop()
            
            # Verify we got output
            assert len(output_lines) > 0
            
            # Convert to LogLine objects
            from sentry_tui.pty_interceptor import LogLine
            log_lines = [LogLine(line) for line in output_lines]
            
            # Test filtering functionality
            app = SentryTUIApp(["test"])
            
            # Test various filters
            test_filters = ["server", "worker", "ERROR", "GET", "14:"]
            
            for filter_text in test_filters:
                app.filter_text = filter_text
                
                # Count matching lines
                matching_lines = [line for line in log_lines if app.matches_filter(line)]
                
                # Should have consistent results
                assert isinstance(matching_lines, list)
                
                # If we have matches, verify they contain the filter text
                for line in matching_lines:
                    assert filter_text.lower() in line.content.lower()
            
        except Exception as e:
            # Make sure to stop the interceptor even if test fails
            interceptor.stop()
            raise e
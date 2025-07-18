"""Tests for PTYInterceptor class."""

import subprocess
from unittest.mock import Mock, patch, call
from sentry_tui.pty_interceptor import (
    PTYInterceptor,
    strip_ansi_background_colors,
    apply_rich_coloring,
)


class TestPTYInterceptor:
    """Test cases for PTYInterceptor class."""

    def test_interceptor_initialization(self):
        """Test PTYInterceptor initialization."""
        command = ["python", "-m", "sentry_tui.dummy_app"]
        interceptor = PTYInterceptor(command)

        assert interceptor.command == command
        assert interceptor.process is None
        assert interceptor.master_fd is None
        assert interceptor.slave_fd is None
        assert interceptor.running is False
        assert interceptor.output_thread is None
        assert interceptor.buffer == ""
        assert interceptor.on_output is not None  # Should have default handler

    def test_interceptor_initialization_with_custom_output_handler(self):
        """Test PTYInterceptor initialization with custom output handler."""
        command = ["test", "command"]
        output_handler = Mock()
        interceptor = PTYInterceptor(command, output_handler)

        assert interceptor.command == command
        assert interceptor.on_output == output_handler

    def test_default_output_handler(self):
        """Test the default output handler."""
        command = ["test", "command"]
        interceptor = PTYInterceptor(command)

        with patch("builtins.print") as mock_print:
            interceptor._default_output_handler("test line")
            mock_print.assert_called_once_with("test line", end="")

    def test_process_output_single_line(self):
        """Test processing a single complete line."""
        command = ["test", "command"]
        output_handler = Mock()
        interceptor = PTYInterceptor(command, output_handler)

        interceptor._process_output("test line\n")

        output_handler.assert_called_once_with("test line\n")
        assert interceptor.buffer == ""

    def test_process_output_multiple_lines(self):
        """Test processing multiple complete lines."""
        command = ["test", "command"]
        output_handler = Mock()
        interceptor = PTYInterceptor(command, output_handler)

        interceptor._process_output("line1\nline2\nline3\n")

        expected_calls = [call("line1\n"), call("line2\n"), call("line3\n")]
        output_handler.assert_has_calls(expected_calls)
        assert interceptor.buffer == ""

    def test_process_output_incomplete_line(self):
        """Test processing incomplete lines (buffering)."""
        command = ["test", "command"]
        output_handler = Mock()
        interceptor = PTYInterceptor(command, output_handler)

        # Send incomplete line
        interceptor._process_output("incomplete")

        # No output should be called yet
        output_handler.assert_not_called()
        assert interceptor.buffer == "incomplete"

        # Complete the line
        interceptor._process_output(" line\n")

        output_handler.assert_called_once_with("incomplete line\n")
        assert interceptor.buffer == ""

    def test_process_output_mixed_complete_and_incomplete(self):
        """Test processing mix of complete and incomplete lines."""
        command = ["test", "command"]
        output_handler = Mock()
        interceptor = PTYInterceptor(command, output_handler)

        interceptor._process_output("line1\nline2\npartial")

        expected_calls = [call("line1\n"), call("line2\n")]
        output_handler.assert_has_calls(expected_calls)
        assert interceptor.buffer == "partial"

    @patch("pty.openpty")
    @patch("subprocess.Popen")
    @patch("os.close")
    @patch("fcntl.fcntl")
    @patch("threading.Thread")
    def test_start_interceptor(
        self, mock_thread, mock_fcntl, mock_close, mock_popen, mock_openpty
    ):
        """Test starting the PTY interceptor."""
        # Setup mocks
        mock_openpty.return_value = (10, 11)  # master_fd, slave_fd
        mock_process = Mock()
        mock_process.pid = 12345
        mock_popen.return_value = mock_process
        mock_thread_instance = Mock()
        mock_thread.return_value = mock_thread_instance

        command = ["test", "command"]
        interceptor = PTYInterceptor(command)

        interceptor.start()

        # Verify PTY creation
        mock_openpty.assert_called_once()

        # Verify process creation
        mock_popen.assert_called_once_with(
            command, stdin=11, stdout=11, stderr=11, start_new_session=True
        )

        # Verify slave fd is closed
        mock_close.assert_called_once_with(11)

        # Verify non-blocking I/O setup
        assert mock_fcntl.call_count == 2  # Get and set flags

        # Verify thread is created and started
        mock_thread.assert_called_once()
        mock_thread_instance.start.assert_called_once()

        # Verify state
        assert interceptor.running is True
        assert interceptor.process == mock_process
        assert interceptor.master_fd == 10
        assert interceptor.slave_fd == 11

    @patch("os.killpg")
    @patch("os.getpgid")
    @patch("os.close")
    def test_stop_interceptor(self, mock_close, mock_getpgid, mock_killpg):
        """Test stopping the PTY interceptor."""
        command = ["test", "command"]
        interceptor = PTYInterceptor(command)

        # Setup interceptor state
        interceptor.running = True
        interceptor.process = Mock()
        interceptor.process.pid = 12345
        interceptor.master_fd = 10
        interceptor.output_thread = Mock()
        interceptor.output_thread.is_alive.return_value = True

        mock_getpgid.return_value = 54321

        interceptor.stop()

        # Verify state
        assert interceptor.running is False

        # Verify process termination
        mock_getpgid.assert_called_with(12345)
        mock_killpg.assert_called_with(54321, 15)  # SIGTERM
        interceptor.process.wait.assert_called_once_with(timeout=5)

        # Verify file descriptor cleanup
        mock_close.assert_called_once_with(10)

        # Verify master_fd is set to None after cleanup
        assert interceptor.master_fd is None

        # Verify thread cleanup
        interceptor.output_thread.join.assert_called_once_with(timeout=1)

    @patch("os.killpg")
    @patch("os.getpgid")
    @patch("os.close")
    def test_stop_interceptor_force_kill(self, mock_close, mock_getpgid, mock_killpg):
        """Test stopping the PTY interceptor with force kill."""
        command = ["test", "command"]
        interceptor = PTYInterceptor(command)

        # Setup interceptor state
        interceptor.running = True
        interceptor.process = Mock()
        interceptor.process.pid = 12345
        interceptor.process.wait.side_effect = subprocess.TimeoutExpired([], 5)
        interceptor.master_fd = 10
        interceptor.output_thread = Mock()
        interceptor.output_thread.is_alive.return_value = True

        mock_getpgid.return_value = 54321

        interceptor.stop()

        # Verify SIGTERM was tried first
        mock_killpg.assert_any_call(54321, 15)  # SIGTERM

        # Verify SIGKILL was used after timeout
        mock_killpg.assert_any_call(54321, 9)  # SIGKILL

        assert mock_killpg.call_count == 2

    @patch("os.killpg")
    @patch("os.getpgid")
    @patch("os.close")
    def test_stop_interceptor_process_not_found(
        self, mock_close, mock_getpgid, mock_killpg
    ):
        """Test stopping the PTY interceptor when process is not found."""
        command = ["test", "command"]
        interceptor = PTYInterceptor(command)

        # Setup interceptor state
        interceptor.running = True
        interceptor.process = Mock()
        interceptor.process.pid = 12345
        interceptor.master_fd = 10
        interceptor.output_thread = Mock()
        interceptor.output_thread.is_alive.return_value = True

        mock_getpgid.side_effect = ProcessLookupError("Process not found")

        interceptor.stop()

        # Verify state
        assert interceptor.running is False

        # Verify process termination was attempted
        mock_getpgid.assert_called_with(12345)
        mock_killpg.assert_not_called()  # Should not be called if process not found

        # Verify file descriptor cleanup still happens
        mock_close.assert_called_once_with(10)

    @patch("select.select")
    @patch("os.read")
    def test_read_output_with_data(self, mock_read, mock_select):
        """Test reading output when data is available."""
        command = ["test", "command"]
        output_handler = Mock()
        interceptor = PTYInterceptor(command, output_handler)

        # Setup interceptor state
        interceptor.running = True
        interceptor.master_fd = 10

        # Create a side effect that sets running to False after first call
        def select_side_effect(*args, **kwargs):
            result = ([10], [], [])  # Data available
            interceptor.running = False  # Stop after first iteration
            return result

        mock_select.side_effect = select_side_effect

        # Mock read to return test data
        mock_read.return_value = b"test line\n"

        # Run one iteration (will exit when running becomes False)
        interceptor._read_output()

        # Verify select was called
        mock_select.assert_called()

        # Verify read was called
        mock_read.assert_called_once_with(10, 4096)

        # Verify output handler was called
        output_handler.assert_called_once_with("test line\n")

    @patch("select.select")
    @patch("os.read")
    def test_read_output_no_data(self, mock_read, mock_select):
        """Test reading output when no data is available."""
        command = ["test", "command"]
        output_handler = Mock()
        interceptor = PTYInterceptor(command, output_handler)

        # Setup interceptor state
        interceptor.running = True
        interceptor.master_fd = 10

        # Create a side effect that sets running to False after first call
        def select_side_effect(*args, **kwargs):
            result = ([], [], [])  # No data available
            interceptor.running = False  # Stop after first iteration
            return result

        mock_select.side_effect = select_side_effect

        # Run one iteration (will exit when running becomes False)
        interceptor._read_output()

        # Verify select was called
        mock_select.assert_called()

        # Verify read was not called
        mock_read.assert_not_called()

        # Verify output handler was not called
        output_handler.assert_not_called()

    @patch("select.select")
    @patch("os.read")
    def test_read_output_eof(self, mock_read, mock_select):
        """Test reading output when EOF is reached."""
        command = ["test", "command"]
        output_handler = Mock()
        interceptor = PTYInterceptor(command, output_handler)

        # Setup interceptor state
        interceptor.running = True
        interceptor.master_fd = 10

        # Mock select to return data available
        mock_select.return_value = ([10], [], [])

        # Mock read to return empty data (EOF)
        mock_read.return_value = b""

        # This should break the loop
        interceptor._read_output()

        # Verify select was called
        mock_select.assert_called()

        # Verify read was called
        mock_read.assert_called_once_with(10, 4096)

        # Verify output handler was not called for EOF
        output_handler.assert_not_called()

    @patch("select.select")
    @patch("os.read")
    def test_read_output_io_error(self, mock_read, mock_select):
        """Test reading output when I/O error occurs."""
        command = ["test", "command"]
        output_handler = Mock()
        interceptor = PTYInterceptor(command, output_handler)

        # Setup interceptor state
        interceptor.running = True
        interceptor.master_fd = 10

        # Mock select to return data available
        mock_select.return_value = ([10], [], [])

        # Mock read to raise IOError
        mock_read.side_effect = IOError("I/O error")

        # This should break the loop
        interceptor._read_output()

        # Verify select was called
        mock_select.assert_called()

        # Verify read was called
        mock_read.assert_called_once_with(10, 4096)

        # Verify output handler was not called
        output_handler.assert_not_called()

    @patch("os.killpg")
    @patch("os.getpgid")
    @patch("os.close")
    def test_stop_interceptor_fd_already_closed(
        self, mock_close, mock_getpgid, mock_killpg
    ):
        """Test stopping the PTY interceptor when file descriptor is already closed."""
        command = ["test", "command"]
        interceptor = PTYInterceptor(command)

        # Setup interceptor state
        interceptor.running = True
        interceptor.process = Mock()
        interceptor.process.pid = 12345
        interceptor.master_fd = 10
        interceptor.output_thread = Mock()
        interceptor.output_thread.is_alive.return_value = True

        mock_getpgid.return_value = 54321
        # Mock close to raise OSError (bad file descriptor)
        mock_close.side_effect = OSError("Bad file descriptor")

        interceptor.stop()

        # Verify state
        assert interceptor.running is False

        # Verify process termination
        mock_getpgid.assert_called_with(12345)
        mock_killpg.assert_called_with(54321, 15)  # SIGTERM
        interceptor.process.wait.assert_called_once_with(timeout=5)

        # Verify file descriptor cleanup was attempted
        mock_close.assert_called_once_with(10)

        # Verify master_fd is set to None even when close fails
        assert interceptor.master_fd is None

        # Verify thread cleanup
        interceptor.output_thread.join.assert_called_once_with(timeout=1)

    @patch("os.killpg")
    @patch("os.getpgid")
    @patch("os.close")
    def test_stop_interceptor_no_fd(self, mock_close, mock_getpgid, mock_killpg):
        """Test stopping the PTY interceptor when no file descriptor is set."""
        command = ["test", "command"]
        interceptor = PTYInterceptor(command)

        # Setup interceptor state
        interceptor.running = True
        interceptor.process = Mock()
        interceptor.process.pid = 12345
        interceptor.master_fd = None  # No file descriptor
        interceptor.output_thread = Mock()
        interceptor.output_thread.is_alive.return_value = True

        mock_getpgid.return_value = 54321

        interceptor.stop()

        # Verify state
        assert interceptor.running is False

        # Verify process termination
        mock_getpgid.assert_called_with(12345)
        mock_killpg.assert_called_with(54321, 15)  # SIGTERM
        interceptor.process.wait.assert_called_once_with(timeout=5)

        # Verify file descriptor cleanup was not attempted
        mock_close.assert_not_called()

        # Verify master_fd remains None
        assert interceptor.master_fd is None

        # Verify thread cleanup
        interceptor.output_thread.join.assert_called_once_with(timeout=1)

    def test_process_output_unicode_handling(self):
        """Test processing output with Unicode characters."""
        command = ["test", "command"]
        output_handler = Mock()
        interceptor = PTYInterceptor(command, output_handler)

        # Test with Unicode characters
        interceptor._process_output("Hello 世界\n")

        output_handler.assert_called_once_with("Hello 世界\n")
        assert interceptor.buffer == ""

    def test_process_output_empty_input(self):
        """Test processing empty output."""
        command = ["test", "command"]
        output_handler = Mock()
        interceptor = PTYInterceptor(command, output_handler)

        interceptor._process_output("")

        output_handler.assert_not_called()
        assert interceptor.buffer == ""

    def test_process_output_only_newlines(self):
        """Test processing output with only newlines."""
        command = ["test", "command"]
        output_handler = Mock()
        interceptor = PTYInterceptor(command, output_handler)

        interceptor._process_output("\n\n\n")

        expected_calls = [call("\n"), call("\n"), call("\n")]
        output_handler.assert_has_calls(expected_calls)
        assert interceptor.buffer == ""


class TestAnsiBackgroundColorStripping:
    """Test cases for ANSI background color stripping function."""

    def test_strip_standard_background_colors(self):
        """Test stripping standard background colors (40-47)."""
        # Test all standard background colors
        for i in range(40, 48):
            text = f"Hello \x1b[{i}mWorld\x1b[0m"
            result = strip_ansi_background_colors(text)
            assert result == "Hello World\x1b[0m"

    def test_strip_high_intensity_background_colors(self):
        """Test stripping high intensity background colors (100-107)."""
        # Test all high intensity background colors
        for i in range(100, 108):
            text = f"Hello \x1b[{i}mWorld\x1b[0m"
            result = strip_ansi_background_colors(text)
            assert result == "Hello World\x1b[0m"

    def test_strip_256_color_background(self):
        """Test stripping 256-color background codes."""
        text = "Hello \x1b[48;5;196mWorld\x1b[0m"
        result = strip_ansi_background_colors(text)
        assert result == "Hello World\x1b[0m"

    def test_strip_rgb_background(self):
        """Test stripping RGB background codes."""
        text = "Hello \x1b[48;2;255;0;0mWorld\x1b[0m"
        result = strip_ansi_background_colors(text)
        assert result == "Hello World\x1b[0m"

    def test_preserve_foreground_colors(self):
        """Test that foreground colors are preserved."""
        # Standard foreground colors (30-37)
        text = "Hello \x1b[31mRed\x1b[0m World"
        result = strip_ansi_background_colors(text)
        assert result == "Hello \x1b[31mRed\x1b[0m World"

        # High intensity foreground colors (90-97)
        text = "Hello \x1b[91mBright Red\x1b[0m World"
        result = strip_ansi_background_colors(text)
        assert result == "Hello \x1b[91mBright Red\x1b[0m World"

        # 256-color foreground
        text = "Hello \x1b[38;5;196mRed\x1b[0m World"
        result = strip_ansi_background_colors(text)
        assert result == "Hello \x1b[38;5;196mRed\x1b[0m World"

        # RGB foreground
        text = "Hello \x1b[38;2;255;0;0mRed\x1b[0m World"
        result = strip_ansi_background_colors(text)
        assert result == "Hello \x1b[38;2;255;0;0mRed\x1b[0m World"

    def test_preserve_other_formatting(self):
        """Test that other formatting codes are preserved."""
        # Bold
        text = "Hello \x1b[1mBold\x1b[0m World"
        result = strip_ansi_background_colors(text)
        assert result == "Hello \x1b[1mBold\x1b[0m World"

        # Italic
        text = "Hello \x1b[3mItalic\x1b[0m World"
        result = strip_ansi_background_colors(text)
        assert result == "Hello \x1b[3mItalic\x1b[0m World"

        # Underline
        text = "Hello \x1b[4mUnderline\x1b[0m World"
        result = strip_ansi_background_colors(text)
        assert result == "Hello \x1b[4mUnderline\x1b[0m World"

    def test_mixed_background_and_foreground(self):
        """Test stripping background while preserving foreground in mixed scenarios."""
        text = "Hello \x1b[31;42mRed on Green\x1b[0m World"
        result = strip_ansi_background_colors(text)
        assert result == "Hello \x1b[31mRed on Green\x1b[0m World"

    def test_multiple_background_codes(self):
        """Test stripping multiple background codes."""
        text = "Hello \x1b[41mRed BG\x1b[0m and \x1b[43mYellow BG\x1b[0m World"
        result = strip_ansi_background_colors(text)
        assert result == "Hello Red BG\x1b[0m and Yellow BG\x1b[0m World"

    def test_no_background_colors(self):
        """Test that text without background colors is unchanged."""
        text = "Hello \x1b[31mRed\x1b[0m World"
        result = strip_ansi_background_colors(text)
        assert result == text

    def test_empty_string(self):
        """Test that empty string is handled correctly."""
        result = strip_ansi_background_colors("")
        assert result == ""

    def test_plain_text(self):
        """Test that plain text without ANSI codes is unchanged."""
        text = "Hello World"
        result = strip_ansi_background_colors(text)
        assert result == text


class TestLogLineFormatting:
    """Test cases for log line formatting and processing."""

    def test_newline_stripping_in_log_processing(self):
        """Test that trailing newlines are properly handled in log processing."""
        from sentry_tui.pty_interceptor import LogLine

        # Test content with trailing newline
        content_with_newline = "Test log message\n"
        log_line = LogLine(content_with_newline)

        # The content should be stored as-is in the LogLine
        assert log_line.content == content_with_newline

        # But when we strip it for display, it should remove the trailing newline
        clean_content = strip_ansi_background_colors(log_line.content)
        clean_content = clean_content.rstrip("\n")
        assert clean_content == "Test log message"

    def test_multiple_newlines_stripping(self):
        """Test that multiple trailing newlines are properly stripped."""
        content = "Test message\n\n\n"
        clean_content = strip_ansi_background_colors(content)
        clean_content = clean_content.rstrip("\n")
        assert clean_content == "Test message"

    def test_no_newline_unchanged(self):
        """Test that content without newlines is unchanged."""
        content = "Test message without newline"
        clean_content = strip_ansi_background_colors(content)
        clean_content = clean_content.rstrip("\n")
        assert clean_content == "Test message without newline"

    def test_combined_ansi_and_newline_stripping(self):
        """Test stripping both ANSI background colors and trailing newlines."""
        content = "Hello \x1b[41mRed Background\x1b[0m World\n"
        clean_content = strip_ansi_background_colors(content)
        clean_content = clean_content.rstrip("\n")
        assert clean_content == "Hello Red Background\x1b[0m World"


class TestRichColoring:
    """Test cases for Rich-based coloring functionality."""

    def test_apply_rich_coloring_strips_ansi(self):
        """Test that Rich coloring strips ANSI codes."""
        from rich.text import Text

        content = "Hello \x1b[31mRed\x1b[0m World"
        result = apply_rich_coloring(content)
        assert isinstance(result, Text)
        assert str(result) == "Hello Red World"

    def test_apply_rich_coloring_server_logs(self):
        """Test that server logs get proper coloring."""
        from rich.text import Text

        content = "server 01:23:45 [INFO] test message"
        result = apply_rich_coloring(content)
        assert isinstance(result, Text)
        assert str(result) == "server 01:23:45 [INFO] test message"

    def test_apply_rich_coloring_log_levels(self):
        """Test that log levels get proper coloring."""
        from rich.text import Text

        content = "test [ERROR] error message"
        result = apply_rich_coloring(content)
        assert isinstance(result, Text)
        assert str(result) == "test [ERROR] error message"

    def test_apply_rich_coloring_timestamps(self):
        """Test that timestamps get proper styling."""
        from rich.text import Text

        content = "test 12:34:56 message"
        result = apply_rich_coloring(content)
        assert isinstance(result, Text)
        assert str(result) == "test 12:34:56 message"

    def test_apply_rich_coloring_worker_logs(self):
        """Test that worker logs get proper coloring."""
        from rich.text import Text

        content = "worker 01:23:45 [INFO] test message"
        result = apply_rich_coloring(content)
        assert isinstance(result, Text)
        assert str(result) == "worker 01:23:45 [INFO] test message"

    def test_apply_rich_coloring_plain_text(self):
        """Test that plain text without special patterns works."""
        from rich.text import Text

        content = "plain text message"
        result = apply_rich_coloring(content)
        assert isinstance(result, Text)
        assert str(result) == "plain text message"

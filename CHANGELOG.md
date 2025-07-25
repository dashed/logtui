# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Enhanced Process Status Bar**: Advanced process monitoring with multiple detection methods
  - **Port Detection**: Shows open ports using `psutil`, `netstat`, or `lsof` for cross-platform compatibility
  - **Resource Monitoring**: Real-time memory usage (MB) and CPU percentage display
  - **Smart Fallbacks**: Multiple detection methods ensure compatibility across different systems
  - **Synchronized Port Detection**: Uses threading events to detect when process is ready for accurate port detection
  - **Port Preservation**: Maintains port information during restart cycles to prevent information loss
  - **Intelligent Ready Detection**: Monitors log output for server startup indicators (e.g., "Running on", "Listening on")
  - **Compact Display**: Efficient layout showing PID, ports, memory, CPU, restart count, and command
- **Command Editing**: Edit the command while the app is running (press `e` key)
  - Modal dialog for editing the command with current and previous command display
  - Updated command is used by restart and auto-restart functionality
  - Shows previous command after editing for reference
  - Keyboard shortcut: `e` key to open edit dialog
- **Enhanced Dependencies**: Added `psutil>=5.9.0` for robust cross-platform process monitoring
- **CLI Tool Installation**: Support for `uv tool install .` to install sentry-tui as a global command-line tool
- **Command-line Interface**: Proper CLI with argument parsing, help text, and version information
  - `--auto-restart` flag for automatic process restart on crashes
  - `--max-lines N` option to control memory usage (default: 10000)
  - `--version` flag to show version information
  - `--help` for comprehensive usage information
- **Global Command Availability**: `sentry-tui` command available system-wide after installation
- **Argument Separation**: Support for `--` separator to prevent conflicts between sentry-tui and target command flags
- **Service Toggle Bar**: Horizontal bar with checkboxes to show/hide specific services in real-time
- **Dynamic service discovery**: Automatically detects and adds toggles for any new services found in logs
- **Smart Toggle All**: Compact button to enable/disable all services at once with smart behavior
  - If all services are enabled, disables all services
  - If any services are disabled, enables all services
  - Maintains consistency with existing toggle behavior
- **Enhanced Status Bar**: Rich status information display with real-time metrics
  - Line count display (total and filtered) with thousands separators
  - Active filter indicators showing current search terms with Rich markup
  - Service count indicators showing discovered services count
  - Performance metrics (logs/sec, memory usage estimation)
  - Real-time updates with 1-second refresh interval via timer
  - Automatic filtered line count calculation on every update
  - Seamless integration with existing filter and service toggle systems
  - Consistent theming using $surface background and $accent borders
  - Compact layout with no gaps between UI elements
- **Improved Focus Management**: Enhanced keyboard navigation with better key bindings
  - Replaced conflicting 'f' and 'l' key bindings with Tab/Shift+Tab focus cycling
  - Added Escape key to unfocus current element and return to app-level focus
  - Fixed FilterInput widget to allow typing all letters including 'f' and 'l'
  - Maintained full keyboard navigation while eliminating typing conflicts
- **Process Management**: Complete process lifecycle control without restarting sentry-tui
  - **Graceful shutdown**: Send SIGTERM to devserver process (key: `s`)
  - **Force quit**: Send SIGKILL to devserver process (key: `k`)
  - **Graceful restart**: Restart devserver using SIGTERM (key: `r`)
  - **Force restart**: Restart devserver using SIGKILL (key: `Shift+R`)
  - **Auto-restart**: Automatically restart devserver on crashes (key: `a`)
  - **Thread-safe synchronization**: Proper locks and events to prevent race conditions
- **Process Status Bar**: Real-time display of process state, PID, restart count, and auto-restart status
- Comprehensive ANSI escape code regex ported from Node.js chalk library for robust terminal output parsing
- ANSI background color stripping function to prevent color bleeding while preserving foreground colors and formatting
- Rich-based coloring system to replace ANSI codes with clean, reliable styling
- Comprehensive test suite using pytest and textual testing framework
- Test configuration with `pytest.ini` for asyncio support
- Shared test fixtures in `conftest.py` for mocking system components
- Unit tests for LogLine class with service extraction and timestamp handling
- Unit tests for PTYInterceptor class with mocking of system calls
- Unit tests for ANSI background color stripping with comprehensive coverage of all color code types
- Unit tests for Rich-based coloring functionality with service name and log level styling
- TUI interaction tests for SentryTUIApp with async support
- Log filtering tests with parametrized test cases
- Integration tests with real dummy app execution
- Test categorization with markers (unit, integration, slow, fast)
- Makefile test targets for different test suites

### Changed
- **Documentation**: Updated README.md with comprehensive installation and usage instructions
  - Added `uv tool install .` as the recommended installation method
  - Updated all examples to use `getsentry devserver` instead of `sentry devserver`
  - Added CLI reference section with all available options and examples
  - Documented `--` separator usage for preventing argument conflicts
- **Log Format Implementation**: Complete rewrite to match real Sentry devserver Honcho format
  - Fixed from incorrect `service_name HH:MM:SS [LEVEL] module.name: message` format
  - Updated to correct `HH:MM:SS service_name | log_message` format from actual Sentry source code analysis
  - Analyzed `/Users/me/aaa/sentry/sentry/src/sentry/runner/commands/devserver.py` for Honcho setup
  - Analyzed `/Users/me/aaa/sentry/sentry/src/sentry/runner/formatting.py` for SentryPrinter format logic
- Updated LogLine implementation to match exact Sentry devserver log format with SentryPrinter + HumanRenderer patterns
- Updated dummy app to emit logs in exact Sentry format with proper ANSI color codes and timestamps
- Updated all tests to use exact Sentry log format patterns instead of simulated formats
- Updated SERVICE_COLORS to match exact Sentry color scheme from source code
- Replaced simple ANSI regex with comprehensive escape code handling for better terminal compatibility
- Updated Makefile to follow modern uv best practices for 2024-2025
- Replaced `uv pip install -e .` with `uv sync` for dependency management
- Added portable timeout handling for cross-platform compatibility
- Enhanced development workflow with `make dev` target
- Added note about `uv run` automatically handling dependency syncing
- Fixed type annotations to satisfy ty type checker requirements
- Updated service extraction regex to support hyphenated service names (e.g., "celery-beat")
- Fixed test data to use correct timestamp format (HH:MM:SS instead of full datetime)

### Fixed
- **Log Format Accuracy**: Fixed completely incorrect log format implementation discovered from real Sentry devserver logs
  - Service extraction now correctly parses `HH:MM:SS service_name | message` format
  - Updated service extraction regex to `^\d{2}:\d{2}:\d{2}\s+([a-zA-Z0-9._-]+)\s*\|`
  - Fixed module name extraction to use service name (limitation of Honcho format)
  - Fixed message extraction to capture everything after pipe separator
  - Updated all test data from old format to new Honcho format
  - All 153 tests now pass with correct format implementation
- **Build System**: Added proper build system configuration for setuptools in pyproject.toml
- **Service Toggle Bar styling**: Fixed height and visibility issues with compact checkbox layout
- **Code quality checks**: Updated Makefile and ruff configuration to exclude git-repos directory
- Integration test method signature compatibility with updated dummy app format
- CSS parsing error: Changed `layers: base, overlay;` to `layers: base overlay;` following Textual CSS syntax
- Reactive variable declarations moved from `__init__` to class level for proper Textual behavior
- Key binding tests now properly handle Input widget focus management
- Threading issues in memory management tests resolved with proper mocking
- Integration test async decorator and timing issues for reliable test execution
- All 88 tests now pass successfully (previously had failing tests due to format mismatches)
- PTY interceptor "Bad file descriptor" error on application quit by adding proper error handling in stop() method
- ANSI background color bleeding in TUI display by stripping background colors while preserving foreground colors
- Log line spacing issues and display artifacts by implementing Rich-based coloring system to replace ANSI codes
- Initial project structure with `uv` package management
- PTY-based interception system for capturing process output while preserving terminal behavior
- Dummy app that simulates Sentry devserver log output with:
  - Colored service prefixes matching Sentry's color scheme
  - Random log intervals (0.5-3 seconds)
  - Graceful Ctrl+C handling
  - Multi-line log entries (tracebacks)
  - Realistic log message patterns
- Interactive TUI application using Textual framework with:
  - Real-time log filtering (case-insensitive substring matching)
  - ANSI color preservation through PTY
  - Keyboard shortcuts for navigation and control
  - Memory management with circular buffer (10,000 lines)
  - Pause/resume functionality
  - Clear logs functionality
- Development tooling:
  - Makefile with common development commands
  - Project entry points for easy CLI access
  - Proper `src/` layout for clean packaging
  - Ruff integration for linting and formatting
  - ty integration for fast type checking
  - Comprehensive code quality checks with `make check`

### Technical Details
- Implements PTY-based interception as outlined in feasibility document
- Uses non-blocking I/O with threaded output reading
- Maintains terminal behavior and interactive capabilities
- Supports signal handling for graceful shutdown
- Thread-safe communication between PTY reader and TUI

### Usage

**Installation:**
```bash
uv tool install .                    # Install as global tool
uv tool install --editable .        # Install editable for development
```

**Basic Usage:**
```bash
sentry-tui -- getsentry devserver --workers            # Run with getsentry devserver
sentry-tui --auto-restart -- getsentry devserver       # Enable auto-restart
sentry-tui --help                                      # Show help
```

**Development:**
- `make run-dummy` - Run the dummy app for testing  
- `make pty-test` - Test PTY interception with dummy app
- `uv run sentry-tui -- <command>` - Run via uv without installing

### Development Commands
- `make dev` - Setup development environment
- `make test` - Run tests
- `make lint` - Lint code with ruff
- `make format` - Format code with ruff
- `make typecheck` - Type check with ty
- `make check` - Run all checks (lint + format + type check)
- `make clean` - Clean up generated files

### Keyboard Shortcuts
- `q` or `Ctrl+C` - Quit application
- `Tab` - Focus next element (filter input ↔ log display)
- `Shift+Tab` - Focus previous element (log display ↔ filter input)
- `Escape` - Unfocus current element and return to app-level focus
- `c` - Clear all logs
- `p` - Toggle pause/resume log capture
- `s` - Graceful shutdown devserver
- `k` - Force quit devserver
- `r` - Restart devserver (graceful)
- `Shift+R` - Force restart devserver
- `a` - Toggle auto-restart functionality
- `e` - Edit command (shows previous command after editing)
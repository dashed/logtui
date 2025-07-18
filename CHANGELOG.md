# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive ANSI escape code regex ported from Node.js chalk library for robust terminal output parsing
- Comprehensive test suite using pytest and textual testing framework
- Test configuration with `pytest.ini` for asyncio support
- Shared test fixtures in `conftest.py` for mocking system components
- Unit tests for LogLine class with service extraction and timestamp handling
- Unit tests for PTYInterceptor class with mocking of system calls
- TUI interaction tests for SentryTUIApp with async support
- Log filtering tests with parametrized test cases
- Integration tests with real dummy app execution
- Test categorization with markers (unit, integration, slow, fast)
- Makefile test targets for different test suites

### Changed
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
- Integration test method signature compatibility with updated dummy app format
- CSS parsing error: Changed `layers: base, overlay;` to `layers: base overlay;` following Textual CSS syntax
- Reactive variable declarations moved from `__init__` to class level for proper Textual behavior
- Key binding tests now properly handle Input widget focus management
- Threading issues in memory management tests resolved with proper mocking
- Integration test async decorator and timing issues for reliable test execution
- All 88 tests now pass successfully (previously had failing tests due to format mismatches)
- PTY interceptor "Bad file descriptor" error on application quit by adding proper error handling in stop() method
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
- `make run-dummy` - Run the dummy app for testing
- `make pty-test` - Test PTY interception with dummy app
- `uv run python -m sentry_tui.pty_interceptor <command>` - Intercept any command

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
- `f` - Focus filter input
- `l` - Focus log display
- `c` - Clear all logs
- `p` - Toggle pause/resume log capture
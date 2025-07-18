# Claude Code Memory for sentry-tui

## Project Overview
This is a TUI (Terminal User Interface) application for intercepting and filtering Sentry devserver logs. It uses PTY-based interception to capture process output while preserving terminal behavior and ANSI color codes.

## Key Components
- **PTYInterceptor**: Core class that handles PTY-based process interception
- **SentryTUIApp**: Main Textual application providing the interactive interface
- **LogLine**: Data class for parsing and extracting metadata from log lines
- **dummy_app**: Test application that simulates Sentry devserver output

## Virtual Environment Setup
This project uses `uv` for fast Python package and project management. To work with the project:

1. **Create virtual environment** (if not exists):
   ```bash
   uv venv
   ```

2. **Activate virtual environment**:
   ```bash
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   uv sync
   ```

Note: `uv` is 10x-100x faster than pip and requires virtual environments by default, promoting better Python development practices.

## Development Commands
- `make dev` - Setup development environment
- `make test` - Run all tests
- `make lint` - Run ruff linting
- `make format` - Format code with ruff
- `make typecheck` - Type check with ty
- `make check` - Run all quality checks

## NEVER RUN THESE COMMANDS
- `make pty-test` - Interactive TUI that requires manual interaction (use pytest instead)
- `make run-dummy` - Interactive dummy app that requires manual interaction (use pytest instead)
- `make serve` - Serves TUI app in web browser, requires manual interaction (use pytest instead)

## Test Commands
- `uv run pytest` - Run all tests
- `uv run pytest tests/test_pty_interceptor.py` - Run PTY interceptor tests
- `uv run pytest -m unit` - Run only unit tests
- `uv run pytest -m integration` - Run only integration tests

## Common Issues & Solutions
1. **"Bad file descriptor" error on quit**: Fixed by adding proper error handling in PTYInterceptor.stop() method
2. **Tests failing**: Use `uv run pytest` to ensure proper environment
3. **Type errors**: Run `make typecheck` to catch issues early

## Architecture Notes
- Uses `uv` for package management and dependency resolution
- Follows `src/` layout for clean packaging
- PTY-based interception preserves terminal behavior and colors
- Thread-safe communication between PTY reader and TUI
- Memory management with circular buffer (10,000 lines)

## Testing Strategy
- Unit tests for individual components with mocking
- Integration tests for end-to-end functionality
- Test categorization with pytest markers (unit, integration, slow, fast)
- Comprehensive test coverage for PTY file descriptor handling
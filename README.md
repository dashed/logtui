# Sentry TUI

A Terminal User Interface (TUI) for intercepting and filtering Sentry development server logs in real-time.

## Overview

Sentry TUI provides an interactive terminal interface for viewing and filtering logs from the Sentry development server. It captures all process output while preserving terminal behavior and offers powerful filtering capabilities to help developers focus on relevant log messages.

## Features

### Currently Implemented

- **Real-time Log Capture**: PTY-based interception preserves colors and terminal behavior
- **Interactive Filtering**: Filter logs as you type with case-insensitive search
- **Service Toggle Bar**: Horizontal checkboxes to show/hide specific services in real-time
- **Process Management**: Complete devserver lifecycle control without restarting sentry-tui
  - **Graceful shutdown** and **force quit** operations
  - **Graceful restart** and **force restart** operations
  - **Auto-restart** functionality for crashed processes
- **Process Status Bar**: Real-time display of process state, PID, restart count, and auto-restart status
- **Service Recognition**: Automatically identifies and color-codes different services (server, worker, webpack, etc.)
- **Rich Text Display**: Clean, colorized output using Rich library
- **Keyboard Navigation**: Focus between filter input and log display
- **Memory Management**: Circular buffer keeps last 10,000 lines
- **Pause/Resume**: Freeze output for detailed inspection
- **Web Browser Support**: Run in browser via `make serve`

### 🚧 Planned Features

See [docs/implementation-status.md](docs/implementation-status.md) for detailed roadmap.

## Installation

### Prerequisites

- Python 3.8+
- [uv](https://github.com/astral-sh/uv) package manager
- Access to Sentry development server

### Setup

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd sentry-tui
   ```

2. **Install dependencies**:
   ```bash
   uv sync
   ```

3. **Activate virtual environment**:
   ```bash
   source .venv/bin/activate
   ```

## Usage

### Basic Usage

Run the TUI with a Sentry development server:

```bash
# Using uv (recommended)
uv run python -m sentry_tui.pty_interceptor sentry devserver --workers

# Or with activated venv
python -m sentry_tui.pty_interceptor sentry devserver --workers

# Enable auto-restart for crashed processes
uv run python -m sentry_tui.pty_interceptor --auto-restart sentry devserver --workers
```

### Web Browser Mode

Run the TUI in your web browser:

```bash
make serve
```

Then navigate to `http://localhost:8000` in your browser.

### Keyboard Shortcuts

**Navigation:**
- **`f`** - Focus filter input
- **`l`** - Focus log display
- **`q`** or **`Ctrl+C`** - Quit application

**Log Management:**
- **`c`** - Clear all logs
- **`p`** - Pause/Resume log capture

**Process Control:**
- **`s`** - Graceful shutdown devserver
- **`k`** - Force quit devserver
- **`r`** - Restart devserver (graceful)
- **`Shift+R`** - Force restart devserver
- **`a`** - Toggle auto-restart functionality

### Filtering

**Text Filtering:**
- Type in the filter box to search logs in real-time
- Search is case-insensitive and matches any part of the log line
- Clear the filter to show all logs again

**Service Filtering:**
- Click checkboxes in the Service Toggle Bar to show/hide specific services
- Combine service toggles with text filtering for precise log viewing
- All services are shown by default

### Process Management

The TUI provides complete control over the devserver process lifecycle:

**Process States:**
- **STOPPED** - Process is not running
- **STARTING** - Process is being started
- **RUNNING** - Process is running normally
- **STOPPING** - Process is being stopped
- **RESTARTING** - Process is restarting
- **CRASHED** - Process has crashed

**Process Control:**
- **Graceful Shutdown** (`s`): Sends SIGTERM to allow clean shutdown
- **Force Quit** (`k`): Sends SIGKILL for immediate termination
- **Graceful Restart** (`r`): Stops with SIGTERM and restarts
- **Force Restart** (`Shift+R`): Stops with SIGKILL and restarts

**Auto-Restart:**
- Toggle with `a` key or `--auto-restart` flag
- Automatically restarts crashed processes
- Configurable maximum restart attempts (default: 5)
- Displays restart count in status bar

## Development

### Quick Start

```bash
# Install dependencies and run tests
make dev
make test

# Run all code quality checks
make check

# View all available commands
make help
```

### Available Commands

- `make test` - Run all tests
- `make lint` - Lint code with ruff
- `make format` - Format code with ruff
- `make typecheck` - Type check with ty
- `make check` - Run all quality checks
- `make clean` - Clean up generated files

### Testing

The project has comprehensive test coverage with 41+ tests:

```bash
# Run all tests
make test

# Run only fast tests
make test-fast

# Run only unit tests
make test-unit
```

### Architecture

The application consists of several key components:

- **PTYInterceptor**: Captures process output using pseudoterminals
- **SentryTUIApp**: Main Textual application with UI components
- **LogLine**: Parses and structures log entries
- **Rich Integration**: Provides clean, colorized output

## Service Recognition

The TUI automatically recognizes and color-codes these Sentry services:

- **server** - Django web server (purple)
- **worker** - Celery worker (yellow)
- **webpack** - Frontend build process (blue)
- **celery-beat** - Periodic task scheduler (pink)
- **relay** - Relay service (red)
- **getsentry-outcomes** - Billing/outcomes service (orange)

## Configuration

### Environment Variables

- `SENTRY_LOG_LEVEL` - Set logging level (DEBUG, INFO, WARNING, ERROR)
- `SENTRY_LOG_FORMAT` - Set log format (HUMAN, MACHINE)

### Sentry DevServer Flags

The TUI supports all standard Sentry devserver flags:

- `--workers` - Include worker processes
- `--celery-beat` - Include celery beat scheduler
- `--prefix/--no-prefix` - Control service name prefixes
- `--pretty/--no-pretty` - Control colored output

## Contributing

### Code Style

- Code is formatted with `ruff`
- Type checking with `ty`
- Tests required for new features
- Follow existing patterns and conventions

### Development Guidelines

1. **Never run interactive commands** like `make pty-test` or `make serve` in automated environments
2. **Use uv for dependency management** - it's 10x-100x faster than pip
3. **Write tests** for all new functionality
4. **Update documentation** when adding features

### Project Structure

```
sentry-tui/
├── src/sentry_tui/
│   ├── __init__.py
│   ├── pty_interceptor.py    # Main application
│   └── dummy_app.py          # Test dummy app
├── tests/
│   └── test_pty_interceptor.py
├── docs/
│   ├── implementation-status.md
│   └── sentry-devserver-tui-log-viewer-feasibility.md
├── Makefile                  # Development commands
├── CLAUDE.md                 # AI development notes
├── pyproject.toml           # Project configuration
└── README.md                # This file
```
## Implementation Status

Current implementation is approximately **65% complete** with solid core functionality. See [docs/implementation-status.md](docs/implementation-status.md) for detailed feature tracking and roadmap.

### Next Steps

1. **DevServer Flag Integration** - Better handling of devserver arguments
2. **Log Level Filtering** - Filter by DEBUG/INFO/WARNING/ERROR
3. **Advanced Filter Modes** - Regex and exact match support
4. **Export Functionality** - Save filtered logs to file

## License

[Add license information here]

## Acknowledgments

- Built with [Textual](https://github.com/Textualize/textual) TUI framework
- Uses [Rich](https://github.com/Textualize/rich) for text styling
- Inspired by tools like `lnav` and `fzf`
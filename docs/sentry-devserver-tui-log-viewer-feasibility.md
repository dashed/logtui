# Sentry DevServer TUI Log Viewer - Feasibility Analysis

## Executive Summary

**VERDICT: HIGHLY FEASIBLE** ✅

Developing a TUI CLI app to intercept and interactively filter Sentry development server logs is not only possible but has strong technical foundations. The project would leverage existing technologies and can be implemented with multiple architectural approaches.

## Table of Contents

- [Current Sentry DevServer Architecture](#current-sentry-devserver-architecture)
- [Log Interception Strategies](#log-interception-strategies)
- [TUI Framework Options](#tui-framework-options)
- [Existing Solutions Analysis](#existing-solutions-analysis)
- [Technical Implementation Approaches](#technical-implementation-approaches)
- [Challenges and Mitigation Strategies](#challenges-and-mitigation-strategies)
- [Recommended Architecture](#recommended-architecture)
- [Implementation Roadmap](#implementation-roadmap)

## Current Sentry DevServer Architecture

### Process Management
- **Honcho**: Sentry uses Honcho (Python port of Foreman) to manage multiple processes
- **Process Structure**: Located in `src/sentry/runner/commands/devserver.py`
  - Main processes defined: `src/sentry/runner/commands/devserver.py:21-27` (`_DEFAULT_DAEMONS`)
  - Process spawning: `src/sentry/runner/commands/devserver.py:511-517` (Honcho Manager setup)
  - Daemon configuration: `src/sentry/runner/commands/devserver.py:255-443` (conditional daemon addition)
  - Each process runs as a separate subprocess managed by Honcho

### Log Flow Architecture
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Individual    │    │     Honcho      │    │   Terminal      │
│   Processes     │───▶│   Manager       │───▶│   Output        │
│ (server/worker) │    │ (stdout/stderr) │    │ (with prefixes) │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Detailed Log Flow with Source References

**1. Process Spawning** (`src/sentry/runner/commands/devserver.py`):
```python
# Line 511-517: Honcho Manager setup
manager = Manager(honcho_printer)
for name, cmd in daemons:
    quiet = bool(name not in (settings.DEVSERVER_LOGS_ALLOWLIST or ()) 
                 and settings.DEVSERVER_LOGS_ALLOWLIST)
    manager.add_process(name, list2cmdline(cmd), quiet=quiet, cwd=cwd)
```

**2. Individual Process Logging** (`src/sentry/logging/handlers.py`):
```python
# Line 87-123: StructLogHandler.emit()
def emit(self, record: logging.LogRecord, logger: logging.Logger | None = None):
    if logger is None:
        logger = get_logger()
    logger.log(**self.get_log_kwargs(record=record))
```

**3. Log Rendering** (`src/sentry/logging/handlers.py`):
```python
# Line 72-85: HumanRenderer formats logs
def __call__(self, logger, name, event_dict):
    level = event_dict.pop("level")
    base = "{} [{}] {}: {}".format(
        now().strftime("%H:%M:%S"),  # Timestamp format
        real_level, 
        event_dict.pop("name", "root"),
        event_dict.pop("event", "")
    )
```

**4. Honcho Output Processing** (`src/sentry/runner/formatting.py`):
```python
# Line 81-119: SentryPrinter.write() 
def write(self, message: honcho.printer.Message):
    name = message.name.rjust(self.width)  # Service name
    
    # Line 110-118: Prefix generation with colors
    prefix = "{name_fg}{name}{reset} {indicator_bg} {reset} ".format(
        name=name.ljust(self.width),
        name_fg="\x1b[38;2;%s;%s;%sm" % SERVICE_COLORS.get(name, blank_color),
        indicator_bg="\x1b[48;2;%s;%s;%sm" % SERVICE_COLORS.get(name, blank_color),
        reset="\x1b[0m",
    )
```

**5. Colorization Pipeline** (`src/sentry/runner/formatting.py`):
```python
# Line 96-106: Log content processing
string = re.sub(r"(?P<method>GET|POST|PUT|HEAD|DELETE) (?P<code>[0-9]{3})", 
                colorize_code, string)                    # HTTP status codes
string = re.sub(r"Gracefully killing worker [0-9]+ .*\.\.\.", 
                colorize_reboot, string)                 # Reboot detection  
string = re.sub(r"WSGI app [0-9]+ \(.*\) ready in [0-9]+ seconds .*", 
                colorize_booted, string)                 # Boot completion
string = re.sub(r"Traceback \(most recent call last\).*", 
                colorize_traceback, string)              # Python tracebacks
```

**Final Output Format**: 
```
[timestamp] [service_name_colored] [colored_indicator] log_content_with_ansi_codes
```

### Logging Configuration
- **Location**: `src/sentry/conf/server.py:1774-1819` (LOGGING config)
- **Handler**: `StructLogHandler` in `src/sentry/logging/handlers.py:87-123`
- **Format**: Structured JSON logs with timestamps, levels, trace IDs
- **Console Output**: Human-readable format via `HumanRenderer` in `src/sentry/logging/handlers.py:72-85`
- **JSON Rendering**: `src/sentry/logging/handlers.py:59-70` (JSONRenderer class)

### Log Formatting and Honcho Integration
- **File**: `src/sentry/runner/formatting.py`
- **Honcho Printer**: `src/sentry/runner/formatting.py:78-120` (`get_honcho_printer` function)
- **Service Colors**: `src/sentry/runner/formatting.py:18-24` (SERVICE_COLORS mapping)
- **Log Colorization**: 
  - HTTP codes: `src/sentry/runner/formatting.py:27-46`
  - Reboot detection: `src/sentry/runner/formatting.py:49-56`
  - Boot completion: `src/sentry/runner/formatting.py:59-66`
  - Traceback highlighting: `src/sentry/runner/formatting.py:69-75`
- **Custom SentryPrinter**: `src/sentry/runner/formatting.py:81-119` (extends honcho.printer.Printer)

## Log Interception Strategies

### 1. Process Wrapper Approach ⭐ **RECOMMENDED**
**Concept**: Create a wrapper script that spawns the devserver and captures all output

```python
# Conceptual implementation
import subprocess
import threading
from textual.app import App

def intercept_devserver():
    process = subprocess.Popen(
        ['sentry', 'devserver', '--workers'],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    
    for line in iter(process.stdout.readline, ''):
        # Parse and forward to TUI
        tui_app.add_log_line(line)
```

**Pros**: 
- Clean separation of concerns
- Preserves original devserver functionality
- Easy to implement
- Can capture all process outputs

**Cons**: 
- May lose some terminal features (colors, interactive input)
- Potential buffering issues

### 2. PTY-Based Interception
**Concept**: Use pseudoterminals to preserve terminal behavior

```python
import pty
import os
import select

def pty_devserver():
    master, slave = pty.openpty()
    process = subprocess.Popen(
        ['sentry', 'devserver', '--workers'],
        stdin=slave, stdout=slave, stderr=slave
    )
    
    # Read from master fd for TUI processing
    while True:
        ready, _, _ = select.select([master], [], [])
        if ready:
            data = os.read(master, 1024)
            # Process and display in TUI
```

**Pros**: 
- Preserves ANSI colors and terminal behavior
- Real-time output capture
- Maintains interactive capabilities

**Cons**: 
- More complex implementation
- Platform-specific considerations

### 3. Log File Monitoring
**Concept**: Configure Sentry to log to files and tail them

**Pros**: 
- Non-intrusive to devserver
- Can persist logs across restarts
- Multiple viewer instances possible

**Cons**: 
- Requires configuration changes
- Potential delay in log visibility
- Doesn't capture stdout from processes

### 4. Honcho Plugin/Modification
**Concept**: Modify Honcho's printer or create a custom manager

**Pros**: 
- Deep integration with process management
- Access to per-process output streams
- Can maintain existing color/formatting

**Cons**: 
- Requires modifying Sentry's devserver code
- More invasive approach

## TUI Framework Options

### 1. Textual ⭐ **RECOMMENDED**
- **Modern Framework**: Built on Rich, async-powered
- **Features**: 16.7M colors, mouse support, smooth animations
- **RichLog Widget**: Perfect for log viewing with scrollable content
- **Active Development**: Well-maintained, growing ecosystem
- **Web Support**: Can run in both terminal and browser

### 2. Rich + Custom Implementation
- **Rich Library**: Excellent text formatting and styling
- **Manual TUI**: Build custom interface components
- **Lighter Weight**: More control over specific features

### 3. Traditional Curses
- **Mature**: Well-established, stable
- **Lightweight**: Minimal dependencies
- **Complex**: More development effort required

### 4. Alternative Options
- **py_curses_tui**: Python TUI library based on curses
- **blessed**: Modern terminal capabilities library

## Existing Solutions Analysis

### Similar Tools in the Ecosystem

#### lnav (Logfile Navigator)
- **Strengths**: Advanced log parsing, SQL queries, real-time tailing
- **Limitations**: File-based, not process-aware
- **Relevance**: Good inspiration for filtering UX

#### nerdlog
- **Strengths**: Multi-host, timeline histogram, real-time
- **Limitations**: SSH-focused, not development-oriented
- **Relevance**: Modern TUI design patterns

#### django-tui
- **Strengths**: Django-specific TUI tools
- **Limitations**: Command management, not log viewing
- **Relevance**: Shows Django ecosystem TUI adoption

### Gap Analysis
**Missing**: No existing tool combines:
- Django/process manager awareness
- Real-time log interception
- Interactive filtering (fzf-style)
- Service-aware log parsing

## Technical Implementation Approaches

### Approach A: Standalone Wrapper Application ⭐

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   sentry-tui    │    │    devserver    │    │   TUI Display   │
│   (wrapper)     │───▶│   (subprocess)  │───▶│   (Textual)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

**Implementation**: 
- New CLI tool: `sentry-tui devserver --workers`
- Subprocess management with stdout/stderr capture
- Real-time log parsing and filtering
- Textual-based interface

### Approach B: Plugin Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Enhanced      │    │   TUI Plugin    │    │   Log Display   │
│   devserver     │───▶│   (embedded)    │───▶│   (overlay)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

**Implementation**:
- Modify devserver command to include `--tui` flag
- Integrate TUI as overlay on existing output
- Hotkey to toggle between normal and TUI modes

### Approach C: Sidecar Process

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   devserver     │    │   Log Bridge    │    │   TUI Viewer    │
│   (unchanged)   │───▶│   (IPC/socket)  │───▶│   (separate)    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

**Implementation**:
- Devserver logs to structured format (JSON lines)
- Bridge process monitors logs and sends via IPC
- Separate TUI application connects to bridge

## Challenges and Mitigation Strategies

### 1. Output Buffering
**Challenge**: Process output may be buffered, causing delays

**Mitigation**:
- Use `bufsize=1` (line buffering) in subprocess calls
- Consider `stdbuf` utility for unbuffered output
- PTY-based approach naturally handles this

### 2. ANSI Color Preservation
**Challenge**: Colors and formatting may be lost in capture

**Mitigation**:
- PTY-based interception preserves colors
- Parse ANSI codes and re-render in TUI
- Textual has excellent ANSI support

### 3. Interactive Input Handling
**Challenge**: DevServer sometimes needs interactive input (pdb, etc.)

**Mitigation**:
- PTY forwarding for stdin
- Hotkey to switch between filter and passthrough modes
- "Interactive mode" that bypasses TUI temporarily

### 4. Performance with High Log Volume
**Challenge**: TUI may become slow with rapid log output

**Mitigation**:
- Ring buffer for log storage (keep last N lines)
- Efficient filtering algorithms
- Async processing with Textual's async capabilities
- Filtering before display (pre-filter expensive operations)

### 5. Service Recognition
**Challenge**: Identifying which service produced each log line

**Mitigation**:
- Parse Honcho's prefix format: `servicename | log content`
- Use Sentry's existing color scheme for services
- Regex parsing of existing format

## Recommended Architecture

### Core Components

```
┌─────────────────────────────────────────────────────────────┐
│                     sentry-tui                             │
├─────────────────────────────────────────────────────────────┤
│  CLI Interface                                              │
│  ├── argparse wrapper for devserver args                   │
│  └── TUI activation options                                │
├─────────────────────────────────────────────────────────────┤
│  Process Manager                                           │
│  ├── subprocess.Popen with PTY                            │
│  ├── Real-time output capture                             │
│  └── Signal handling (Ctrl+C, etc.)                       │
├─────────────────────────────────────────────────────────────┤
│  Log Parser                                                │
│  ├── Service prefix extraction (from Honcho format)       │
│  ├── Timestamp parsing (HH:MM:SS format)                  │
│  ├── Log level detection (from structlog)                 │
│  └── ANSI code handling (preserve colors)                 │
├─────────────────────────────────────────────────────────────┤
│  Filter Engine                                            │
│  ├── Fuzzy search (fzf-style)                            │
│  ├── Regex support                                       │
│  ├── Service filtering (based on SERVICE_COLORS)         │
│  ├── Log level filtering                                 │
│  └── Time range filtering                                │
├─────────────────────────────────────────────────────────────┤
│  TUI Interface (Textual)                                  │
│  ├── Main log display (RichLog widget)                   │
│  ├── Filter input bar                                    │
│  ├── Service toggle sidebar                              │
│  ├── Status bar (stats, keybindings)                     │
│  └── Help overlay                                        │
└─────────────────────────────────────────────────────────────┘
```

### Key Source Code Integration Points

**Log Parser Component** needs to understand:
- **Honcho prefix format**: `src/sentry/runner/formatting.py:110-118` (prefix generation)
- **Service names**: `src/sentry/runner/commands/devserver.py:21-27` (available services)
- **Timestamp format**: `src/sentry/logging/handlers.py:76-77` (HumanRenderer timestamp)
- **ANSI color codes**: `src/sentry/runner/formatting.py:27-75` (colorization patterns)

**Service Filtering** should use:
- **SERVICE_COLORS mapping**: `src/sentry/runner/formatting.py:18-24`
- **Process quiet flags**: `src/sentry/runner/commands/devserver.py:513-516` (DEVSERVER_LOGS_ALLOWLIST)

## DevServer Flags That Impact Log Behavior

### CLI Flags (`src/sentry/runner/commands/devserver.py:52-145`)

#### **Log Display Control:**
- **`--prefix/--no-prefix`** (default: `True`) - `src/sentry/runner/commands/devserver.py:84-87`
  - Controls service name prefix and timestamp display
  - When disabled, removes Honcho's service prefixes from output
  - **Impact**: TUI needs to handle both prefixed and non-prefixed modes

- **`--pretty/--no-pretty`** (default: `False`) - `src/sentry/runner/commands/devserver.py:94-97`
  - Enables stylized outputs with colors and formatting
  - Activates `SentryPrinter` colorization (`src/sentry/runner/formatting.py:83-84`)
  - **Impact**: When enabled, log lines contain ANSI color codes

#### **Global Log Options** (via `@log_options()` decorator):
- **`--loglevel/-l`** - `src/sentry/runner/decorators.py:56-63`
  - Values: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`, `FATAL`
  - Environment variable: `SENTRY_LOG_LEVEL`
  - **Impact**: Controls verbosity of all logging output

- **`--logformat`** - `src/sentry/runner/decorators.py:64-70`
  - Values: `HUMAN`, `MACHINE` (`src/sentry/logging/__init__.py:1-4`)
  - Environment variable: `SENTRY_LOG_FORMAT`
  - **Impact**: Changes between human-readable and machine-readable JSON format

#### **Process Control Flags** (affecting log volume):
- **`--workers/--no-workers`** - Adds worker processes and their logs
- **`--celery-beat/--no-celery-beat`** - Adds celery beat scheduler logs
- **`--ingest/--no-ingest`** - Adds ingest service logs (including Relay)
- **`--taskworker/--no-taskworker`** - Adds Kafka-based task worker logs
- **`--dev-consumer/--no-dev-consumer`** - Consolidates multiple Kafka consumers into one process

### Configuration Settings (`src/sentry/conf/server.py`)

#### **Service Log Filtering:**
- **`DEVSERVER_LOGS_ALLOWLIST`** - `src/sentry/conf/server.py:3637`
  ```python
  # Set to an iterable of strings matching services so only logs from those services show up
  # eg. DEVSERVER_LOGS_ALLOWLIST = {"server", "webpack", "worker"}
  DEVSERVER_LOGS_ALLOWLIST: set[str] | None = None
  ```
  - **Usage**: `src/sentry/runner/commands/devserver.py:514-515`
  - **Impact**: When set, only specified services produce visible logs

#### **HTTP Request Log Filtering:**
- **`DEVSERVER_REQUEST_LOG_EXCLUDES`** - `src/sentry/conf/server.py:3646`
  ```python
  # Filter for logs of incoming requests, which matches on substrings
  # e.g., add "/api/0/relays/" to suppress all relays endpoint logs
  DEVSERVER_REQUEST_LOG_EXCLUDES: list[str] = []
  ```
  - **Usage**: `src/sentry/runner/commands/devserver.py:458-461`
  - **Implementation**: Creates regex pattern via uWSGI's `log-drain` option
  - **Impact**: Prevents specific HTTP request patterns from appearing in logs

### Environment Variables

#### **Development Environment:**
- **`SENTRY_ENVIRONMENT`** - Set to "development" by devserver
- **`SENTRY_LOG_LEVEL`** - Global logging level override
- **`SENTRY_LOG_FORMAT`** - Format override (human/machine)
- **`SENTRY_DEVSERVER_BIND`** - Can be set via environment instead of argument

#### **Logging Configuration:**
- **`SENTRY_DEVSERVICES_DSN`** - Controls Sentry SDK initialization
- **`SENTRY_LOG_API_ACCESS`** - Controls API access logging (`src/sentry/conf/server.py:3648`)

### uWSGI Log Format Control (`src/sentry/runner/commands/devserver.py:445-461`)

#### **Conditional Log Formats:**
```python
# With daemons (multiple processes):
"log-format": "%(method) %(status) %(uri) %(proto) %(size)"

# Without daemons (single process):  
"log-format": "[%(ltime)] %(method) %(status) %(uri) %(proto) %(size)"
```

#### **Request Filtering:**
- Uses uWSGI's `log-drain` option with regex patterns
- Built from `DEVSERVER_REQUEST_LOG_EXCLUDES` setting
- **Note**: Complex regex patterns have known issues (see comment at line 453)

### TUI Implementation Considerations for Flags

#### **Flag Pass-Through Strategy:**
The TUI wrapper should:
1. **Accept all devserver flags** and pass them through unchanged
2. **Add TUI-specific flags** (e.g., `--tui-filter-mode`, `--tui-no-colors`)
3. **Detect flag impacts** and adjust parsing accordingly

#### **Critical Flag Handling:**

**`--prefix/--no-prefix` Detection:**
```python
# TUI must detect this flag and adjust log parsing
if '--no-prefix' in args:
    # Parse logs without service prefixes: "timestamp message"
    log_parser.prefix_mode = False
else:
    # Parse logs with Honcho prefixes: "service | timestamp message"  
    log_parser.prefix_mode = True
```

**`--pretty/--no-pretty` Detection:**
```python
# Affects ANSI code handling
if '--pretty' in args:
    # Expect ANSI color codes in output
    log_parser.ansi_enabled = True
else:
    # Plain text output
    log_parser.ansi_enabled = False
```

**`--logformat` Impact:**
```python
# Must handle both human and machine formats
if logformat == 'machine':
    # Expect JSON log lines: {"timestamp": "...", "level": "INFO", "event": "..."}
    log_parser.format = LogFormat.JSON
else:
    # Expect human format: "14:32:01 [INFO] service.module: message"
    log_parser.format = LogFormat.HUMAN
```

#### **Configuration Integration:**
The TUI should also read and respect:
- **`DEVSERVER_LOGS_ALLOWLIST`** - Use as default service filter
- **`DEVSERVER_REQUEST_LOG_EXCLUDES`** - Pre-filter HTTP request logs
- **`SENTRY_LOG_LEVEL`** - Set default minimum log level filter

## GetSentry DevServer Log Flow

### How `getsentry devserver --workers` Works

#### **Command Entry Point** (`/Users/me/aaa/sentry/getsentry/getsentry/__main__.py:9-16`):
```python
def main() -> int:
    os.environ.pop("SENTRY_CONF", None)
    sys.argv.insert(1, f"--config={_HERE}/settings.py")
    
    from sentry.__main__ import main as sentry_main
    
    sentry_main()
    return 0
```

**Log Flow Summary**:
```
getsentry devserver --workers
    ↓
getsentry.__main__.main() 
    ↓ (injects --config=getsentry/settings.py)
sentry.__main__.main()
    ↓ (loads getsentry config)
sentry.runner.commands.devserver()
    ↓ (spawns processes with additional getsentry services)
Honcho Manager + SentryPrinter
    ↓
Terminal Output with getsentry-specific processes
```

#### **Configuration Loading** (`/Users/me/aaa/sentry/getsentry/getsentry/settings.py:17-26`):
```python
if "GETSENTRY_DJANGO_CONF" in os.environ:
    DJANGO_CONF = os.environ["GETSENTRY_DJANGO_CONF"]
else:
    DJANGO_CONF = os.environ.get("DJANGO_CONF", "dev")
if DJANGO_CONF != "defaults":
    config = "getsentry.conf.settings.%s" % DJANGO_CONF
    # Loads getsentry.conf.settings.dev by default
```

#### **Configuration Chain** (for development):
1. **Base Sentry Config**: `src/sentry/conf/server.py` - Core Sentry settings
2. **GetSentry Defaults**: `getsentry/conf/settings/defaults.py:11` - `from sentry.conf.server import *`
3. **GetSentry Dev Config**: `getsentry/conf/settings/dev.py:6` - `from getsentry.conf.settings.defaults import *`

#### **Additional Processes Added by GetSentry** (`getsentry/conf/settings/dev.py:205-209`):
```python
# Add the outcome consumer to devserver so that billing data works out of the box.
DEVSERVER_START_KAFKA_CONSUMERS.append("getsentry-outcomes")

# Patch the default topic to be outcomes-billing which has more interesting data.
SENTRY_KAFKA_CONSUMERS["getsentry-outcomes"]["topic"] = Topic.OUTCOMES_BILLING
```

### Complete GetSentry DevServer Process List

When running `getsentry devserver --workers`, the processes include:

#### **Core Sentry Processes** (from `src/sentry/runner/commands/devserver.py:21-27`):
- **`server`** - Django web server
- **`worker`** - Celery worker for background tasks  
- **`celery-beat`** - Periodic task scheduler (if `--celery-beat`)
- **`taskworker`** - Kafka-based task workers (if `--taskworker`)

#### **Kafka Consumers** (conditionally added with `--workers`):
- **Standard Sentry consumers** (from `settings.DEVSERVER_START_KAFKA_CONSUMERS`)
- **`getsentry-outcomes`** - **Additional GetSentry consumer** for billing data

#### **Frontend Process** (if `--watchers`):
- **`webpack`** - Frontend build process with hot reload

### GetSentry-Specific Log Content

#### **Additional Log Sources**:
1. **Billing & Outcomes Processing**: `getsentry-outcomes` consumer processes billing events
2. **Customer-Specific Features**: Additional API endpoints and business logic
3. **Integration Services**: Extended integrations beyond core Sentry

#### **Configuration Differences**:
- **Development hostname**: `dev.getsentry.net:8000` vs `localhost:8000`
- **Multi-region setup**: Customer domain simulation
- **Extended CSP policies**: Additional trusted sources
- **Billing service integration**: Stripe, AvaTax, outcome processing

### TUI Implementation Considerations for GetSentry

#### **Service Recognition**:
The TUI parser needs to recognize the additional `getsentry-outcomes` service:
```python
# Extended SERVICE_COLORS should include:
GETSENTRY_SERVICE_COLORS = {
    **SERVICE_COLORS,  # From sentry/runner/formatting.py:18-24  
    "getsentry-outcomes": (255, 165, 0),  # Orange for billing/outcomes
}
```

#### **Log Volume Expectations**:
- **Higher log volume** due to additional services
- **Billing-related logs** from outcomes processing
- **Customer simulation traffic** in development

#### **Configuration Detection**:
```python
# TUI should detect GetSentry vs core Sentry
def detect_sentry_mode():
    if "--config" in sys.argv and "getsentry" in str(sys.argv):
        return "getsentry"
    return "sentry"
```

### Source Code References Summary

**GetSentry DevServer Entry Points**:
- Command entry: `/Users/me/aaa/sentry/getsentry/getsentry/__main__.py:9-16`
- Config injection: `/Users/me/aaa/sentry/getsentry/getsentry/settings.py:17-26`
- Dev settings: `/Users/me/aaa/sentry/getsentry/getsentry/conf/settings/dev.py`
- Additional consumer: `/Users/me/aaa/sentry/getsentry/getsentry/conf/settings/dev.py:205-209`

**Core Sentry DevServer (still applies)**:
- Process management: `src/sentry/runner/commands/devserver.py:511-517`
- Log formatting: `src/sentry/runner/formatting.py:78-120`
- Service colors: `src/sentry/runner/formatting.py:18-24`

### Key Features

1. **Real-time Filtering**: As-you-type filter updates
2. **Service Awareness**: Toggle visibility per service (server, worker, etc.)
3. **Multiple Filter Modes**: Fuzzy, regex, exact match
4. **Log Level Filtering**: Show/hide by severity
5. **Export Options**: Save filtered results to file
6. **Keyboard Navigation**: Vim-style shortcuts
7. **Search History**: Remember previous filter patterns
8. **Pause/Resume**: Freeze output for detailed inspection

### User Interface Design

```
┌─────────────────────────────────────────────────────────────────────────┐
│ sentry-tui devserver --workers                           [?] Help [q] Quit │
├─────────────────────────────────────────────────────────────────────────┤
│ Filter: █                                                  Lines: 1,234   │
├─────────────────────────────────────────────────────────────────────────┤
│ [✓] server  [✓] worker  [✓] celery-beat  [ ] webpack                    │
├─────────────────────────────────────────────────────────────────────────┤
│ 14:32:01 server  | GET 200 /api/0/projects/                             │
│ 14:32:01 worker  | Task completed: sentry.tasks.process_event            │
│ 14:32:02 server  | POST 201 /api/0/events/                              │
│ 14:32:02 worker  | Processing event id=abc123...                        │
│ █                                                                        │
│                                                                          │
│ ... (scrollable log content)                                            │
│                                                                          │
├─────────────────────────────────────────────────────────────────────────┤
│ / Search  Space Pause  ↑↓ Scroll  Tab Services  Ctrl+C Exit             │
└─────────────────────────────────────────────────────────────────────────┘
```

## Implementation Roadmap

### Phase 1: Core Infrastructure (2-3 weeks)
- [ ] CLI argument parsing and devserver process spawning
- [ ] Basic PTY-based output capture
- [ ] Simple Textual app with log display
- [ ] Service prefix parsing from Honcho output

### Phase 2: Filtering Engine (1-2 weeks)
- [ ] Real-time filter input box
- [ ] Basic fuzzy search implementation
- [ ] Service-based filtering toggles
- [ ] Log level filtering

### Phase 3: Advanced Features (2-3 weeks)
- [ ] Regex filter support
- [ ] Search history and persistence
- [ ] Export functionality
- [ ] Performance optimizations (ring buffer, async)

### Phase 4: Polish and UX (1-2 weeks)
- [ ] Keyboard shortcuts and help system
- [ ] Error handling and edge cases
- [ ] Configuration file support
- [ ] Documentation and examples

### Phase 5: Integration and Testing (1 week)
- [ ] Integration with existing Sentry workflow
- [ ] Cross-platform testing
- [ ] Performance testing with high log volumes
- [ ] User acceptance testing

**Total Estimated Development Time**: 7-11 weeks

## Conclusion

The development of a TUI CLI app for intercepting and filtering Sentry devserver logs is **highly feasible** and would provide significant value to developers working with Sentry. The technical foundation exists with mature libraries (Textual, subprocess management, PTY handling), and the implementation can be done with relatively low risk.

**Key Success Factors**:
1. **Leverage Existing Patterns**: Build on proven TUI design patterns from tools like lnav and fzf
2. **Incremental Development**: Start with basic functionality and add features iteratively
3. **Community Feedback**: Early prototype testing with Sentry developers
4. **Performance Focus**: Ensure responsiveness even with high log volume

**Recommended Next Steps**:
1. Create a minimal prototype with basic log capture and display
2. Test with actual Sentry devserver workloads
3. Gather feedback from Sentry development team
4. Refine the UX based on real usage patterns

The project has strong potential to become a valuable development tool that could even be considered for integration into the main Sentry repository.
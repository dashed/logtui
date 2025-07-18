# Makefile for sentry-tui development

.PHONY: sync run-dummy test-dummy pty-test clean help dev test lint format check typecheck

# Sync dependencies (explicit sync for CI or when needed)
sync:
	uv sync

# Run the dummy app for testing
run-dummy:
	uv run python -m sentry_tui.dummy_app

# Test the dummy app briefly (portable timeout)
test-dummy:
	@if command -v gtimeout >/dev/null 2>&1; then \
		gtimeout 5 uv run python -m sentry_tui.dummy_app || true; \
	elif command -v timeout >/dev/null 2>&1; then \
		timeout 5 uv run python -m sentry_tui.dummy_app || true; \
	else \
		echo "No timeout command available, skipping test-dummy"; \
	fi

# Test PTY-based interception with dummy app
pty-test:
	uv run python -m sentry_tui.pty_interceptor python -m sentry_tui.dummy_app

# Development workflow - sync and run tests
dev: sync
	@echo "Development environment ready!"

# Run tests
test:
	uv run pytest

# Lint code with ruff
lint:
	uv run ruff check .

# Format code with ruff
format:
	uv run ruff format .

# Type check with ty
typecheck:
	uv run ty check .

# Check code (lint + format check + type check)
check:
	uv run ruff check .
	uv run ruff format --check .
	uv run ty check .

# Clean up generated files
clean:
	rm -rf .venv
	rm -rf __pycache__
	rm -rf src/sentry_tui/__pycache__
	rm -rf .pytest_cache
	rm -rf build
	rm -rf dist
	rm -rf *.egg-info

# Show help
help:
	@echo "Available targets:"
	@echo "  sync       - Sync dependencies (uv handles this automatically with uv run)"
	@echo "  run-dummy  - Run the dummy app for testing"
	@echo "  test-dummy - Test the dummy app briefly"
	@echo "  pty-test   - Test PTY-based interception"
	@echo "  dev        - Setup development environment"
	@echo "  test       - Run tests"
	@echo "  lint       - Lint code with ruff"
	@echo "  format     - Format code with ruff"
	@echo "  typecheck  - Type check with ty"
	@echo "  check      - Check code (lint + format + type check)"
	@echo "  clean      - Clean up generated files"
	@echo "  help       - Show this help message"
	@echo ""
	@echo "Note: uv run automatically syncs dependencies, so you rarely need 'make sync'"
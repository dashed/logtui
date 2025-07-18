# Makefile for sentry-tui development

.PHONY: sync run-dummy test-dummy pty-test clean help dev test test-unit test-integration test-fast test-slow lint format check typecheck

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

# Test PTY-based interception with dummy app (press 'q' or Ctrl+C to exit)
pty-test:
	uv run python -m sentry_tui.pty_interceptor python -m sentry_tui.dummy_app

# Development workflow - sync and run tests
dev: sync
	@echo "Development environment ready!"

# Run all tests
test:
	uv run pytest tests/

# Run unit tests only (fast)
test-unit:
	uv run pytest tests/ -m "unit" -v

# Run integration tests only (slow)
test-integration:
	uv run pytest tests/ -m "integration" -v

# Run fast tests (exclude slow tests)
test-fast:
	uv run pytest tests/ -m "not slow" -v

# Run slow tests only
test-slow:
	uv run pytest tests/ -m "slow" -v

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
	@echo "  sync            - Sync dependencies (uv handles this automatically with uv run)"
	@echo "  run-dummy       - Run the dummy app for testing"
	@echo "  test-dummy      - Test the dummy app briefly"
	@echo "  pty-test        - Test PTY-based interception (press 'q' or Ctrl+C to exit)"
	@echo "  dev             - Setup development environment"
	@echo ""
	@echo "Testing:"
	@echo "  test            - Run all tests"
	@echo "  test-unit       - Run unit tests only (fast)"
	@echo "  test-integration - Run integration tests only (slow)"
	@echo "  test-fast       - Run fast tests (exclude slow tests)"
	@echo "  test-slow       - Run slow tests only"
	@echo ""
	@echo "Code Quality:"
	@echo "  lint            - Lint code with ruff"
	@echo "  format          - Format code with ruff"
	@echo "  typecheck       - Type check with ty"
	@echo "  check           - Check code (lint + format + type check)"
	@echo ""
	@echo "Maintenance:"
	@echo "  clean           - Clean up generated files"
	@echo "  help            - Show this help message"
	@echo ""
	@echo "Note: uv run automatically syncs dependencies, so you rarely need 'make sync'"
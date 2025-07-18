# Makefile for sentry-tui development

.PHONY: install run-dummy test-dummy pty-test clean help

# Install dependencies
install:
	uv pip install -e .

# Run the dummy app for testing
run-dummy:
	uv run python -m sentry_tui.dummy_app

# Test the dummy app briefly
test-dummy:
	timeout 5 uv run python -m sentry_tui.dummy_app || true

# Test PTY-based interception with dummy app
pty-test:
	uv run python -m sentry_tui.pty_interceptor python -m sentry_tui.dummy_app

# Clean up
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
	@echo "  install    - Install dependencies"
	@echo "  run-dummy  - Run the dummy app for testing"
	@echo "  test-dummy - Test the dummy app briefly"
	@echo "  pty-test   - Test PTY-based interception"
	@echo "  clean      - Clean up generated files"
	@echo "  help       - Show this help message"
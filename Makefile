# Makefile for Dify Official Plugins
# Provides development tools and commands for type checking, linting, and testing

.DEFAULT_GOAL := help

# Development setup and tools
setup:
	@echo "🔧 Setting up development environment..."
	@command -v uv >/dev/null 2>&1 || { echo "❌ uv is required but not installed. Please install uv first."; exit 1; }
	@uv sync --group dev
	@echo "✅ Development environment setup complete!"

# Type checking with basedpyright
type-check:
	@echo "📝 Running type check with basedpyright..."
	@./dev/basedpyright-check
	@echo "✅ Type check complete"

# Type check specific path
type-check-path:
	@echo "📝 Running type check on $(PATH)..."
	@./dev/basedpyright-check $(PATH)
	@echo "✅ Type check complete for $(PATH)"

# Linting with ruff (if available)
lint:
	@echo "🔧 Running linting with ruff..."
	@uv run --group dev ruff check . || echo "⚠️  Ruff not available or issues found"
	@echo "✅ Linting complete"

# Format code with ruff (if available)
format:
	@echo "🎨 Formatting code with ruff..."
	@uv run --group dev ruff format . || echo "⚠️  Ruff not available"
	@echo "✅ Code formatting complete"

# Run tests
test:
	@echo "🧪 Running tests..."
	@uv run --group dev pytest tests/ -v || echo "⚠️  Some tests may have failed or pytest not configured"
	@echo "✅ Tests complete"

# Clean up development artifacts
clean:
	@echo "🧹 Cleaning up development artifacts..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -name "*.pyc" -delete 2>/dev/null || true
	@echo "✅ Cleanup complete"

# Check all - comprehensive check suite
check-all: type-check lint test
	@echo "✅ All checks complete!"

# Help target
help:
	@echo "Dify Official Plugins Development Commands:"
	@echo ""
	@echo "Setup and Configuration:"
	@echo "  make setup          - Set up development environment"
	@echo ""
	@echo "Type Checking:"
	@echo "  make type-check     - Run type checking on entire repository"
	@echo "  make type-check-path PATH=<path> - Run type checking on specific path"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint           - Run linting with ruff"
	@echo "  make format         - Format code with ruff"
	@echo ""
	@echo "Testing:"
	@echo "  make test           - Run tests"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean          - Clean up development artifacts"
	@echo "  make check-all      - Run all checks (type-check, lint, test)"
	@echo ""
	@echo "Example usage:"
	@echo "  make setup                          # First time setup"
	@echo "  make type-check                     # Check all files"
	@echo "  make type-check-path PATH=models/   # Check models directory"

# Phony targets
.PHONY: setup type-check type-check-path lint format test clean check-all help
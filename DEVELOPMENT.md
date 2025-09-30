# Development Guide for Dify Official Plugins

This guide covers development tools and best practices for working with the Dify Official Plugins repository.

## Type Checking with BasedPyright

We use [BasedPyright](https://github.com/detachhead/basedpyright) for static type checking to catch type-related bugs and improve code quality.

### Quick Start

```bash
# Run type checking on entire repository
make type-check

# Run type checking on specific path
make type-check-path PATH=models/gemini

# Alternative: use script directly
./dev/basedpyright-check models/gemini
```

### Setup

The repository includes development dependencies and configuration for BasedPyright:

- **pyproject.toml**: Contains BasedPyright development dependency
- **pyrightconfig.json**: BasedPyright configuration settings
- **dev/basedpyright-check**: Wrapper script for running type checks
- **Makefile**: Convenient targets for common tasks

### Configuration

Type checking is configured with reasonable defaults in `pyrightconfig.json`:

- **Type checking mode**: `basic` (moderate strictness)
- **Python version**: 3.12
- **Missing imports**: Disabled (due to plugin dependencies)
- **Unknown types**: Disabled (relaxed for plugin development)
- **Useful checks**: Enabled (unused imports, unnecessary casts, etc.)

### Running Type Checks

#### Command Line

```bash
# Full repository type check
./dev/basedpyright-check

# Specific plugin type check
./dev/basedpyright-check models/openai
./dev/basedpyright-check tools/google_search

# Using make targets
make type-check
make type-check-path PATH=tools/
```

#### IDE Integration

BasedPyright works with most Python IDEs:

- **VS Code**: Install the [BasedPyright extension](https://marketplace.visualstudio.com/items?itemName=ms-pyright.pyright)
- **PyCharm**: Configure external tool or use Pyright plugin
- **Vim/Neovim**: Use with LSP clients like coc.nvim or native LSP

### CI/CD Integration

Type checking is integrated into GitHub Actions:

1. **Pre-check workflow**: Runs type checking on changed plugins
2. **Type check workflow**: Dedicated workflow for type checking
3. **Automatic execution**: Triggered on Python file changes

### Understanding Type Check Output

BasedPyright provides different types of messages:

```
# Error - must be fixed
error: "split" is not a known attribute of "None"

# Warning - should be addressed  
warning: TypeVar appears only once in generic function signature

# Note - informational
note: Variable is declared but never used
```

### Common Issues and Solutions

#### Missing Import Errors

For plugin dependencies that aren't installed in the CI environment:

```json
{
  "reportMissingImports": false
}
```

This is already configured in our setup.

#### Plugin-Specific Dependencies

Each plugin may have its own dependencies. Type checking focuses on:

- Type safety within the plugin code
- Proper use of Dify plugin interfaces
- General Python type correctness

#### False Positives

If BasedPyright reports false positives, you can:

1. **Add type comments**: `# type: ignore`
2. **Update configuration**: Adjust settings in `pyrightconfig.json`
3. **Use type assertions**: `cast()` function for complex cases

### Development Workflow

1. **Write code** with type hints when possible
2. **Run type checks** regularly during development
3. **Fix type errors** before committing
4. **CI will verify** type checking passes

### Best Practices

#### Type Hints

```python
# Good: Clear type hints
def process_text(text: str, max_length: int) -> str:
    return text[:max_length]

# Better: Use generic types for complex structures
from typing import List, Dict, Optional

def analyze_data(items: List[Dict[str, str]]) -> Optional[Dict[str, int]]:
    if not items:
        return None
    return {"count": len(items)}
```

#### Plugin Interface Types

```python
# Use Dify plugin types when available
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class MyTool(Tool):
    def _invoke(self, user_id: str, tool_parameters: dict) -> ToolInvokeMessage:
        # Implementation
        pass
```

#### Handling External Libraries

```python
# For external libraries without type stubs
try:
    import some_external_library  # type: ignore
except ImportError:
    some_external_library = None
```

## Other Development Tools

### Code Formatting

```bash
# Format code (if ruff is available)
make format

# Check code style  
make lint
```

### Testing

```bash
# Run tests
make test

# Run all checks
make check-all
```

### Cleanup

```bash
# Clean development artifacts
make clean
```

## Getting Help

- **Type checking issues**: Check BasedPyright documentation
- **Plugin development**: See individual plugin READMEs
- **CI/CD issues**: Check GitHub Actions logs
- **General questions**: See main Dify documentation

## Contributing

When contributing:

1. Ensure type checking passes: `make type-check`
2. Follow existing code patterns
3. Add type hints to new code
4. Update tests if needed

For more information, see the main [CONTRIBUTING.md](https://github.com/langgenius/dify/blob/main/CONTRIBUTING.md) in the Dify repository.
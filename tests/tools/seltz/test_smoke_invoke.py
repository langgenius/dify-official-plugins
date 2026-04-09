import os
import sys
import importlib.util
import types

PLUGIN_DIR = os.path.join("tools", "seltz")


def load_module_from_path(module_name: str, file_path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader, f"cannot load spec for {module_name} from {file_path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def test_tool_python_loadable():
    """Test that the tool python file is importable and defines expected class."""
    tool_py = os.path.join(PLUGIN_DIR, "tools", "seltz_search.py")
    tmod = load_module_from_path("seltz_search", tool_py)
    tool_cls = getattr(tmod, "SeltzSearchTool")
    assert callable(getattr(tool_cls, "_invoke"))


def test_provider_python_loadable():
    """Test that the provider python file is importable when plugin path is set."""
    # Add plugin directory to path so relative imports work
    plugin_abs_path = os.path.abspath(PLUGIN_DIR)
    sys.path.insert(0, plugin_abs_path)
    try:
        provider_py = os.path.join(PLUGIN_DIR, "provider", "seltz.py")
        mod = load_module_from_path("seltz_provider", provider_py)
        assert hasattr(mod, "SeltzProvider")
    finally:
        sys.path.remove(plugin_abs_path)

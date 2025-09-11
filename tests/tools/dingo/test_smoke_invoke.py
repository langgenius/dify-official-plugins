import os
import importlib.util
import types

PLUGIN_DIR = os.path.join('tools', 'dingo')


def load_module_from_path(module_name: str, file_path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader, f"cannot load spec for {module_name} from {file_path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def test_provider_python_loadable_and_tool_present():
    # provider python should be importable
    provider_py = os.path.join(PLUGIN_DIR, 'provider', 'dingo.py')
    mod = load_module_from_path('dingo_provider', provider_py)
    assert hasattr(mod, 'DingoProvider')

    # tool python should be importable and define expected class and _invoke
    tool_py = os.path.join(PLUGIN_DIR, 'tools', 'text_quality_evaluator.py')
    tmod = load_module_from_path('dingo_text_quality_evaluator', tool_py)
    tool_cls = getattr(tmod, 'TextQualityEvaluatorTool')
    assert callable(getattr(tool_cls, '_invoke'))


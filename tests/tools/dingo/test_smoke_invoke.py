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

    # All tools must load with the plugin's declared dependencies.
    for filename, class_name in (
        ('keyword_matcher', 'KeywordMatcher'),
        ('resume_optimizer', 'ResumeOptimizerTool'),
        ('dingo_scout', 'DingoScout'),
    ):
        tool_py = os.path.join(PLUGIN_DIR, 'tools', f'{filename}.py')
        tmod = load_module_from_path(f'dingo_{filename}', tool_py)
        tool_cls = getattr(tmod, class_name)
        assert callable(getattr(tool_cls, '_invoke'))

import os
import importlib.util
import types

from dify_plugin import DifyPluginEnv, Plugin

PLUGIN_DIR = os.path.join('tools', 'dingo')


def load_module_from_path(module_name: str, file_path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    assert spec and spec.loader, f"cannot load spec for {module_name} from {file_path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def test_smoke_invoke_text_quality_tool():
    # load provider python to get the Tool class without package install
    provider_py = os.path.join(PLUGIN_DIR, 'provider', 'dingo.py')
    mod = load_module_from_path('dingo_provider', provider_py)

    # Provider should expose TextQualityEvaluatorTool via import path ..tools.text_quality_evaluator
    provider_cls = getattr(mod, 'DingoProvider')
    provider = provider_cls()
    provider._set_tools()
    assert provider.tools, 'provider.tools should not be empty'

    # find our tool
    tool = None
    for t in provider.tools:
        if t.__class__.__name__ == 'TextQualityEvaluatorTool':
            tool = t
            break
    assert tool is not None, 'TextQualityEvaluatorTool not found from provider'

    # do a minimal invoke
    msg = tool._invoke('test-user', {'text_content': 'Hello world'})
    # The ToolInvokeMessage has .text attribute
    assert hasattr(msg, 'text')
    assert 'Quality' in msg.text or 'quality' in msg.text


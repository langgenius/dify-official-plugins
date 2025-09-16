import os
import importlib.util
import types
import inspect
from collections.abc import Generator

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

    # do a minimal invoke; support both legacy and new signatures, and generator outputs
    params = {'text_content': 'Hello world'}
    sig = inspect.signature(tool._invoke)
    if len(sig.parameters) == 2:  # (self, tool_parameters)
        res = tool._invoke(params)
    else:  # (self, user_id, tool_parameters)
        res = tool._invoke('test-user', params)

    # normalize to first ToolInvokeMessage
    if isinstance(res, Generator) or (hasattr(res, '__iter__') and not hasattr(res, 'text')):
        msg = next(iter(res))
    else:
        msg = res

    # The ToolInvokeMessage has .text attribute
    assert hasattr(msg, 'text')
    assert 'Quality' in msg.text or 'quality' in msg.text


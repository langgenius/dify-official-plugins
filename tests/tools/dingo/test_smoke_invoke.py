import os
import importlib
import importlib.util
import types
import inspect
import sys
from collections.abc import Generator

from dify_plugin import DifyPluginEnv, Plugin

PLUGIN_DIR = os.path.join('tools', 'dingo')

# Ensure project root is importable as a package root
if os.getcwd() not in sys.path:
    sys.path.insert(0, os.getcwd())


def test_smoke_invoke_text_quality_tool():
    # load provider python to get the Tool class without package install
    mod = importlib.import_module('tools.dingo.provider.dingo')

    # Provider should expose a tool instance
    provider_cls = getattr(mod, 'DingoProvider')
    provider = provider_cls()
    provider._set_tools()
    assert provider.tools, 'provider.tools should not be empty'

    # find our tool (accept either legacy TextQualityEvaluatorTool or new DingoTool)
    tool = None
    for t in provider.tools:
        if t.__class__.__name__ in ('TextQualityEvaluatorTool', 'DingoTool'):
            tool = t
            break
    assert tool is not None, 'Expected TextQualityEvaluatorTool or DingoTool from provider'

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

    # The ToolInvokeMessage should contain text (either as .text or .message.text)
    has_text_attr = hasattr(msg, 'text') or (hasattr(msg, 'message') and hasattr(msg.message, 'text'))
    assert has_text_attr
    text_value = getattr(msg, 'text', None) or getattr(getattr(msg, 'message', None), 'text', '')
    assert 'Quality' in text_value or 'quality' in text_value




def test_rule_list_multiple_selection_smoke():
    mod = importlib.import_module('tools.dingo.provider.dingo')
    provider_cls = getattr(mod, 'DingoProvider')
    provider = provider_cls()
    provider._set_tools()
    assert provider.tools
    tool = provider.tools[0]

    params = {
        'text_content': 'Hello world',
        'rule_list': ['RuleEnterAndSpace', 'RuleContentNull']
    }
    sig = inspect.signature(tool._invoke)
    res = tool._invoke(params) if len(sig.parameters) == 2 else tool._invoke('u', params)

    # Should yield a ToolInvokeMessage
    if isinstance(res, Generator) or (hasattr(res, '__iter__') and not hasattr(res, 'text')):
        msg = next(iter(res))
    else:
        msg = res
    has_text_attr = hasattr(msg, 'text') or (hasattr(msg, 'message') and hasattr(msg.message, 'text'))
    assert has_text_attr
    text_value = getattr(msg, 'text', None) or getattr(getattr(msg, 'message', None), 'text', '')
    assert 'Quality' in text_value or 'quality' in text_value

import sys, types, pathlib

# Point to the plugin directory
plugin_dir = pathlib.Path(__file__).parent
sys.path.insert(0, str(plugin_dir))

# Create minimal stubs for dify_plugin SDK so we don't need to install it
if 'dify_plugin' not in sys.modules:
    dp = types.ModuleType('dify_plugin')

    class Tool:
        def create_text_message(self, text: str):
            class Msg:
                def __init__(self, t: str):
                    self.text = t
                def __repr__(self):
                    return f"<ToolInvokeMessage text={self.text!r}>"
            return Msg(text)

    # Top-level placeholders (not used in this test, but provided for completeness)
    dp.Tool = Tool
    dp.DifyPluginEnv = object
    dp.Plugin = object

    # Submodule: dify_plugin.entities.tool.ToolInvokeMessage
    entities = types.ModuleType('dify_plugin.entities')
    tool_mod = types.ModuleType('dify_plugin.entities.tool')
    class ToolInvokeMessage:  # placeholder type
        pass
    tool_mod.ToolInvokeMessage = ToolInvokeMessage

    # Wire modules
    sys.modules['dify_plugin'] = dp
    sys.modules['dify_plugin.entities'] = entities
    sys.modules['dify_plugin.entities.tool'] = tool_mod

# Import the tool under test
from tools.text_quality_evaluator import TextQualityEvaluatorTool  # type: ignore


def run_case(text: str, group: str = 'default') -> str:
    tool = TextQualityEvaluatorTool()
    msg = tool._invoke(user_id='dev', tool_parameters={'text_content': text, 'rule_group': group})
    # The stub returns an object with .text attribute
    return getattr(msg, 'text', str(msg))


if __name__ == '__main__':
    print('=== Dingo Text Quality Tool Smoke Test ===')
    out = run_case('Hello, this is a short sample text for quality check.')
    print(out)


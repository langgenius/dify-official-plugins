from dify_plugin import ToolProvider
import importlib.util
from pathlib import Path


def _load_text_quality_tool():
    # Try absolute import first
    try:
        from tools.dingo.tools.text_quality_evaluator import TextQualityEvaluatorTool  # type: ignore
        return TextQualityEvaluatorTool
    except Exception:
        pass
    # Try package-relative import if available
    try:
        from ..tools.text_quality_evaluator import TextQualityEvaluatorTool  # type: ignore
        return TextQualityEvaluatorTool
    except Exception:
        pass
    # Fallback: load by file path to work when module is loaded directly
    plugin_root = Path(__file__).resolve().parents[1]  # .../tools/dingo
    tool_path = plugin_root / 'tools' / 'text_quality_evaluator.py'
    spec = importlib.util.spec_from_file_location('dingo_text_quality_evaluator', str(tool_path))
    assert spec and spec.loader, f"cannot load spec for {tool_path}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return getattr(mod, 'TextQualityEvaluatorTool')


class DingoProvider(ToolProvider):
    def _set_tools(self):
        TextQualityEvaluatorTool = _load_text_quality_tool()
        self.tools = [TextQualityEvaluatorTool()]


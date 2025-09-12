from dify_plugin import ToolProvider
from ..tools.text_quality_evaluator import TextQualityEvaluatorTool


class DingoProvider(ToolProvider):
    def _set_tools(self):
        self.tools = [TextQualityEvaluatorTool()]

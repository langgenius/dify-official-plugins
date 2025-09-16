from dify_plugin import ToolProvider
from ..tools.text_quality_evaluator import DingoTool


class DingoProvider(ToolProvider):
    def _set_tools(self):
        # Register the generic DingoTool (backward compatible with TextQualityEvaluatorTool)
        self.tools = [DingoTool()]

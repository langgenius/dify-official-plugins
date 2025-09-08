from dify_plugin import Provider
from ..tools.text_quality_evaluator import TextQualityEvaluatorTool


class DingoProvider(Provider):
    def _set_tools(self):
        self.tools = [TextQualityEvaluatorTool()]


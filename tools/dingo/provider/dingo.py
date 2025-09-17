from dify_plugin import ToolProvider
from ..tools.text_quality_evaluator import DingoTool


class DingoProvider(ToolProvider):
    def _set_tools(self):
        # Register the generic DingoTool (backward compatible with TextQualityEvaluatorTool)
        # During unit tests we may not have a real runtime/session; pass None to satisfy constructor.
        try:
            self.tools = [DingoTool(runtime=None, session=None)]  # type: ignore[arg-type]
        except TypeError:
            # Fallback if SDK signature is different
            self.tools = [DingoTool()]  # type: ignore[call-arg]

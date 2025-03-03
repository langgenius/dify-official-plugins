from tools.feishu_group_bot import FeishuGroupBotTool
from dify_plugin import ToolProvider


class FeishuProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict) -> None:
        FeishuGroupBotTool()

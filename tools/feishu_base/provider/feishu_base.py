from dify_plugin import ToolProvider
from tools.feishu_api_utils import auth


class FeishuBaseProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict) -> None:
        auth(credentials)

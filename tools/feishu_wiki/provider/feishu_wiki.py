from dify_plugin import ToolProvider
from feishu_api_utils import auth


class FeishuWikiProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict) -> None:
        auth(credentials)

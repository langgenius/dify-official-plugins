from dify_plugin import ToolProvider
from feishu_task_api_v2_utils import auth


class FeishuTaskProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict) -> None:
        auth(credentials)

from dify_plugin import ToolProvider
from tools.lark_api_utils import lark_auth


class LarkDocumentProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict) -> None:
        lark_auth(credentials)

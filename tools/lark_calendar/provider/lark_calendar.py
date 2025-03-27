from dify_plugin import ToolProvider
from lark_api_utils import lark_auth


class LarkCalendarProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict) -> None:
        lark_auth(credentials)

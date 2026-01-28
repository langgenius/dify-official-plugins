from dify_plugin import ToolProvider
from typing import Any

class SomarkProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        """
        校验凭证是否有效
        """
        # 暂时不做严格校验，直接通过
        pass

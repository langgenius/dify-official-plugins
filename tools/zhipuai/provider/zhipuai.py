"""Provide the input parameters type for the cogview provider class"""

from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.cogview import CogViewTool


class ZhipuAIProvider(ToolProvider):
    """ZhipuAI provider"""

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            for _ in CogViewTool.from_credentials(credentials).invoke(
                tool_parameters={
                    "prompt": "一个城市在水晶瓶中欢快生活的场景，水彩画风格，展现出微观与珠宝般的美丽。",
                    "model": "cogview-3-flash",
                    "size": "1024x1024",
                }
            ):
                pass

        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e)) from e

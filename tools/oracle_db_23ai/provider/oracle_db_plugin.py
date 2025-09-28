from typing import Any
from dify_plugin import ToolProvider


class OracleDbPluginProvider(ToolProvider):
    
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        # 此插件不需要OAuth功能，不执行凭证验证
        # 空实现以满足Dify插件系统的接口要求
        pass

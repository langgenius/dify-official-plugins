from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.partition import PartitionTool
from tools.transform import TransformTool


class UnstructuredProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        try:
            if credentials.get("server_type") == "transform":
                TransformTool.validate_credentials(credentials)
                return
            instance = PartitionTool.from_credentials(credentials)
            assert isinstance(instance, PartitionTool)
            instance.validate_api_url()
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

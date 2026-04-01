import requests
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import ToolProvider


class SiliconflowProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, str]) -> None:
        url = "https://api.siliconflow.cn/v1/models"
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {credentials.get('siliconFlow_api_key')}",
        }
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code != 200:
            raise ToolProviderCredentialValidationError(
                "SiliconFlow API key is invalid"
            )

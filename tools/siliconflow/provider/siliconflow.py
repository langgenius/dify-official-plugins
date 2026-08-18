import requests
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import ToolProvider

from utils.endpoint import get_base_url


class SiliconflowProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, str]) -> None:
        base_url = get_base_url(credentials)
        url = f"{base_url}/v1/models"
        headers = {
            "accept": "application/json",
            "authorization": f"Bearer {credentials.get('siliconFlow_api_key')}",
        }
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 401:
            raise ToolProviderCredentialValidationError(
                f"SiliconFlow API key was rejected by {base_url} "
                f"(HTTP 401). If your key is from the other SiliconFlow site "
                f"(siliconflow.cn vs siliconflow.com), change the "
                f"'Use International Endpoint' setting to match it."
            )
        if response.status_code != 200:
            raise ToolProviderCredentialValidationError(
                f"SiliconFlow credential validation against {url} failed "
                f"with HTTP {response.status_code}: {response.text[:200]}"
            )

import requests
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import ToolProvider


class GiteeAIToolProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict) -> None:
        url = "https://ai.gitee.com/api/base/account/me"
        headers = {"accept": "application/json", "authorization": f"Bearer {credentials.get('api_key')}"}
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise ToolProviderCredentialValidationError("GiteeAI API key is invalid")

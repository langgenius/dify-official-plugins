from typing import Any
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import ToolProvider
from fish_audio_sdk import Session

class FishaudioProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        api_key = credentials.get("api_key")
        api_base = credentials.get("api_base")
        session = Session(api_key, base_url=api_base)
        try:
            models = session.list_models(self_only=True)
        except Exception:
            raise ToolProviderCredentialValidationError("Fish audio API key is invalid")

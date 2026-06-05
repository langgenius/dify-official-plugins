from typing import Any

from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import ToolProvider
from openai import OpenAI

from openai_client import normalize_openai_base_url


class OpenAIProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        base_url = credentials.get("openai_base_url")
        api_key = credentials.get("openai_api_key")
        organization_id = credentials.get("openai_organization_id")

        try:
            client = OpenAI(
                api_key=api_key,
                base_url=normalize_openai_base_url(base_url),
                organization=organization_id,
            )

            client.models.list()
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

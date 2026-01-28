from typing import Any
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import ToolProvider
from openai import OpenAI
from yarl import URL


class OpenAIProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        base_url = credentials.get("openai_base_url")
        api_key = credentials.get("openai_api_key")
        organization_id = credentials.get("openai_organization_id")

        try:
            # Initialize OpenAI client with credentials
            client = OpenAI(
                api_key=api_key,
                base_url=str(URL(base_url) / "v1") if base_url else None,
                organization=organization_id
            )
            
            # Test the API with a simple request
            response = client.chat.completions.create(
                model="gpt-4.1-nano",
                messages=[{"role": "user", "content": "Tell me a joke."}],
                max_tokens=10
            )
            
            # If we get here without exception, credentials are valid
            print(f"API test successful: {response.choices[0].message.content}")
            
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

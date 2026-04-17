import logging
from urllib.parse import urljoin

import requests
from dify_plugin import ModelProvider
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)


class NVIDIANIMProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: dict) -> None:
        endpoint_url = credentials.get("endpoint_url", "").rstrip("/")
        api_key = credentials.get("api_key", "").strip()

        if not endpoint_url:
            raise CredentialsValidateFailedError("API endpoint URL is required")

        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        models_url = urljoin(f"{endpoint_url}/", "models")

        try:
            response = requests.get(models_url, headers=headers, timeout=10)
            if response.status_code == 200:
                return
            if response.status_code == 401:
                raise CredentialsValidateFailedError("Invalid API key. Please check your API key.")
            if response.status_code == 404:
                raise CredentialsValidateFailedError(
                    f"Endpoint not found: {models_url}. For hosted NVIDIA NIM use https://integrate.api.nvidia.com/v1; for self-hosted use http://<host>:8000/v1."
                )
            raise CredentialsValidateFailedError(
                f"Failed to validate credentials: HTTP {response.status_code}, response body: {response.text}"
            )
        except requests.exceptions.ConnectionError as e:
            raise CredentialsValidateFailedError(f"Failed to connect to {endpoint_url}: {str(e)}")
        except requests.exceptions.Timeout:
            raise CredentialsValidateFailedError(f"Connection timeout while connecting to {endpoint_url}")
        except CredentialsValidateFailedError:
            raise
        except Exception as e:
            logger.exception("Failed to validate NVIDIA NIM credentials")
            raise CredentialsValidateFailedError(f"Failed to validate credentials: {str(e)}")

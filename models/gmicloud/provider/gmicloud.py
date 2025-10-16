import logging
from collections.abc import Mapping
import requests

from dify_plugin import ModelProvider
from dify_plugin.errors.model import CredentialsValidateFailedError

logger = logging.getLogger(__name__)


class GmicloudModelProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: Mapping) -> None:
        """
        Validate provider credentials
        if validate failed, raise exception

        :param credentials: provider credentials, credentials form defined in `provider_credential_schema`.
        """
        try:
            # Validate by making a simple API call to the GMI Cloud endpoint
            api_key = credentials.get("gmicloud_api_key")
            if not api_key:
                raise CredentialsValidateFailedError("GMI Cloud API key is required")
            
            endpoint_url = credentials.get("endpoint_url", "https://api.gmi-serving.com")
            
            # Make a simple request to verify credentials
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            }
            
            # Try to get models list to validate the API key
            response = requests.get(
                f"{endpoint_url}/v1/models",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 401 or response.status_code == 403:
                raise CredentialsValidateFailedError(
                    f"Invalid API key or unauthorized access"
                )
            elif response.status_code != 200:
                raise CredentialsValidateFailedError(
                    f"Failed to validate credentials: HTTP {response.status_code}"
                )
                
            logger.info("GMI Cloud credentials validated successfully")
            
        except CredentialsValidateFailedError as ex:
            raise ex
        except requests.exceptions.RequestException as ex:
            logger.exception("Failed to connect to GMI Cloud API")
            raise CredentialsValidateFailedError(f"Connection error: {str(ex)}")
        except Exception as ex:
            logger.exception(
                f"{self.get_provider_schema().provider} credentials validate failed"
            )
            raise CredentialsValidateFailedError(str(ex))

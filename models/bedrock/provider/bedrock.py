import logging
from collections.abc import Mapping
import boto3
from botocore.exceptions import ClientError

from dify_plugin import ModelProvider
from dify_plugin.entities.model import ModelType
from dify_plugin.errors.model import CredentialsValidateFailedError
from .get_bedrock_client import get_bedrock_client

logger = logging.getLogger(__name__)


class AmazonBedrockModelProvider(ModelProvider):
    def validate_provider_credentials(self, credentials: Mapping) -> None:
        """
        Validate provider credentials
        if validate failed, raise exception

        :param credentials: provider credentials, credentials form defined in `provider_credential_schema`.
        """
        try:
            model_instance = self.get_model_instance(ModelType.LLM)
            # Use `amazon.nova-pro-v1:0` model by default for validating credentials
            model_for_validation = credentials.get("model_for_validation", "amazon.nova-pro-v1:0")
            model_instance.validate_credentials(model=model_for_validation, credentials=credentials)
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            logger.exception(f"{self.get_provider_schema().provider} credentials validate failed")
            raise ex

    def validate_model_credentials(self, model: str, model_type: ModelType, credentials: Mapping) -> None:
        """
        Validate model credentials for custom models (inference profiles)
        
        :param model: model name
        :param model_type: model type
        :param credentials: model credentials
        """
        try:
            if model_type == ModelType.LLM:
                # Check if this is an inference profile based custom model
                inference_profile_id = credentials.get("inference_profile_id")
                if inference_profile_id:
                    # Validate inference profile
                    self._validate_inference_profile(inference_profile_id, credentials)
                else:
                    # Fallback to regular model validation
                    model_instance = self.get_model_instance(model_type)
                    model_instance.validate_credentials(model=model, credentials=credentials)
            else:
                # For non-LLM types, use regular validation
                model_instance = self.get_model_instance(model_type)
                model_instance.validate_credentials(model=model, credentials=credentials)
        except CredentialsValidateFailedError as ex:
            raise ex
        except Exception as ex:
            logger.exception(f"Model {model} credentials validate failed")
            raise CredentialsValidateFailedError(str(ex))

    def _validate_inference_profile(self, inference_profile_id: str, credentials: Mapping) -> None:
        """
        Validate inference profile by calling Bedrock API
        
        :param inference_profile_id: inference profile identifier
        :param credentials: credentials containing AWS access info
        """
        try:
            bedrock_client = get_bedrock_client("bedrock", credentials)
            
            # Call get-inference-profile API
            response = bedrock_client.get_inference_profile(
                inferenceProfileIdentifier=inference_profile_id
            )
            
            # Check if profile is active
            if response.get('status') != 'ACTIVE':
                raise CredentialsValidateFailedError(f"Inference profile {inference_profile_id} is not active")
                
            logger.info(f"Successfully validated inference profile: {inference_profile_id}")
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                raise CredentialsValidateFailedError(f"Inference profile {inference_profile_id} not found")
            elif error_code == 'AccessDeniedException':
                raise CredentialsValidateFailedError(f"Access denied to inference profile {inference_profile_id}")
            else:
                raise CredentialsValidateFailedError(f"Failed to validate inference profile: {str(e)}")
        except Exception as e:
            raise CredentialsValidateFailedError(f"Failed to validate inference profile: {str(e)}")


"""
Shared utility functions for Bedrock inference profiles
"""
import logging
from typing import Dict, Any
from botocore.exceptions import ClientError
from dify_plugin.errors.model import CredentialsValidateFailedError
from provider.get_bedrock_client import get_bedrock_client

logger = logging.getLogger(__name__)


def get_inference_profile_info(inference_profile_id: str, credentials: dict) -> dict:
    """
    Get inference profile information from Bedrock API
    
    :param inference_profile_id: inference profile identifier
    :param credentials: credentials containing AWS access info
    :return: inference profile information
    """
    try:
        bedrock_client = get_bedrock_client("bedrock", credentials)
        
        # Call get-inference-profile API
        response = bedrock_client.get_inference_profile(
            inferenceProfileIdentifier=inference_profile_id
        )
        
        return response
        
    except Exception as e:
        logger.error(f"Failed to get inference profile info: {str(e)}")
        raise e


def validate_inference_profile(inference_profile_id: str, credentials: dict) -> None:
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


def extract_model_id_from_arn(model_arn: str) -> str:
    """
    Extract model ID from ARN
    e.g., 'arn:aws:bedrock:region::foundation-model/anthropic.claude-3-7-sonnet-20250219-v1:0' 
          -> 'anthropic.claude-3-7-sonnet-20250219-v1:0'
    
    :param model_arn: Model ARN
    :return: Model ID
    """
    if "foundation-model/" in model_arn:
        return model_arn.split("foundation-model/")[1]
    return None


def extract_model_info_from_profile(profile_info: dict) -> Dict[str, Any]:
    """
    Extract model information from inference profile
    
    :param profile_info: Inference profile information from AWS
    :return: Dictionary containing model_id and model_type
    """
    underlying_models = profile_info.get("models", [])
    if not underlying_models:
        return None
    
    first_model_arn = underlying_models[0].get("modelArn", "")
    model_id = extract_model_id_from_arn(first_model_arn)
    
    if not model_id:
        return None
    
    # Extract model type from model ID
    if model_id.startswith('anthropic.'):
        model_type = 'anthropic claude'
    elif model_id.startswith('amazon.nova'):
        model_type = 'amazon nova'
    elif model_id.startswith('meta.'):
        model_type = 'meta'
    elif model_id.startswith('mistral.'):
        model_type = 'mistral'
    elif model_id.startswith('ai21.'):
        model_type = 'ai21'
    elif model_id.startswith('deepseek.'):
        model_type = 'deepseek'
    elif model_id.startswith('amazon.'):
        model_type = 'amazon'
    elif model_id.startswith('cohere.'):
        model_type = 'cohere'
    else:
        model_type = None
    
    return {
        'model_id': model_id,
        'model_type': model_type,
        'model_arn': first_model_arn
    }
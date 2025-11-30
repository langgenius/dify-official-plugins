"""
Shared utility functions for Bedrock inference profiles
"""
import logging
import threading
import time
from typing import Dict, Any
from botocore.exceptions import ClientError
from dify_plugin.errors.model import CredentialsValidateFailedError
from provider.get_bedrock_client import get_bedrock_client

logger = logging.getLogger(__name__)

# Cache for inference profile info with 5 minutes TTL
_inference_profile_cache = {}
_CACHE_TTL = 300  # 5 minutes
_cache_lock = threading.Lock()

def get_inference_profile_info(inference_profile_id: str, credentials: dict) -> dict:
    """
    Get inference profile information from Bedrock API with 5-minute caching
    High-frequency calls will cause GetInferenceProfile throttling.

    
    :param inference_profile_id: inference profile identifier
    :param credentials: credentials containing AWS access info
    :return: inference profile information
    """
    current_time = time.time()
    
    # Create cache key based on profile ID and AWS region
    aws_region = credentials.get('aws_region', 'default')
    cache_key = f"{inference_profile_id}:{aws_region}"
    
    # Check if cached data exists and is still valid
    with _cache_lock:
        # Check if cached data exists and is still valid
        if cache_key in _inference_profile_cache:
            cached_data, timestamp = _inference_profile_cache[cache_key]
            if current_time - timestamp < _CACHE_TTL:
                logger.debug(f"Using cached inference profile info for {inference_profile_id}")
                return cached_data
            else:
                # Remove expired cache entry
                logger.debug(f"Cache expired for inference profile {inference_profile_id}, fetching fresh data")
                del _inference_profile_cache[cache_key]
    
    try:
        logger.debug(f"[get_inference_profile_info] credentials: {credentials}")
        bedrock_client = get_bedrock_client("bedrock", credentials)
        
        # Call get-inference-profile API
        response = bedrock_client.get_inference_profile(
            inferenceProfileIdentifier=inference_profile_id
        )
        
        with _cache_lock:
            # Double-check again before caching
            # (another thread might have cached it while we were calling API)
            if cache_key not in _inference_profile_cache:
                _inference_profile_cache[cache_key] = (response, time.time())
                logger.debug(f"Cached inference profile info for {inference_profile_id} (cache size: {len(_inference_profile_cache)})")
            else:
                # Another thread already cached it, that's fine
                cached_data, _ = _inference_profile_cache[cache_key]
                logger.debug(f"Another thread cached {inference_profile_id}, using existing cache")
                return cached_data
        
        return response
        
    except Exception as e:
        logger.error(f"Failed to get inference profile info: {str(e)}")
        raise e


def validate_inference_profile(inference_profile_id: str, credentials: dict) -> None:
    """
    Validate inference profile by calling Bedrock API (uses cached data if available)
    
    :param inference_profile_id: inference profile identifier
    :param credentials: credentials containing AWS access info
    """
    try:
        # Use cached get_inference_profile_info if available
        response = get_inference_profile_info(inference_profile_id, credentials)
        
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
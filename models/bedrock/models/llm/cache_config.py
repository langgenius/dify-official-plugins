"""
Configuration for Bedrock prompt cache feature
"""
import logging

logger = logging.getLogger(__name__)

# Models that support prompt caching
CACHE_SUPPORTED_MODELS = [
    "anthropic.claude-sonnet-4-20250514-v1:0",
    "anthropic.claude-opus-4-20250514-v1:0",
    "anthropic.claude-3-7-sonnet-20250219-v1:0",
    "anthropic.claude-3-5-haiku-20241022-v1:0",
    # "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "amazon.nova-micro-v1:0",
    "amazon.nova-lite-v1:0",
    "amazon.nova-pro-v1:0",
    "amazon.nova-premier-v1:0"
]

# Cache configuration for each model
CACHE_CONFIG = {
    "anthropic.claude-sonnet-4-20250514-v1:0": {
        "min_tokens": 1024,
        "max_checkpoints": 4,
        "supported_fields": ["system", "messages", "tools"]
    },
    "anthropic.claude-opus-4-20250514-v1:0": {
        "min_tokens": 1024,
        "max_checkpoints": 4,
        "supported_fields": ["system", "messages", "tools"]
    },
    "anthropic.claude-3-7-sonnet-20250219-v1:0": {
        "min_tokens": 1024,
        "max_checkpoints": 4,
        "supported_fields": ["system", "messages", "tools"]
    },
    "anthropic.claude-3-5-haiku-20241022-v1:0": {
        "min_tokens": 2048,
        "max_checkpoints": 4,
        "supported_fields": ["system", "messages", "tools"]
    },
    "amazon.nova-micro-v1:0": {
        "min_tokens": 1024,
        "max_checkpoints": 4,
        "supported_fields": ["system", "messages"]
    },
    "amazon.nova-lite-v1:0": {
        "min_tokens": 1024,
        "max_checkpoints": 4,
        "supported_fields": ["system", "messages"]
    },
    "amazon.nova-pro-v1:0": {
        "min_tokens": 1024,
        "max_checkpoints": 4,
        "supported_fields": ["system", "messages"]
    },
    "amazon.nova-premier-v1:0": {
        "min_tokens": 1024,
        "max_checkpoints": 4,
        "supported_fields": ["system", "messages"]
    }
}

def is_cache_supported(model_id: str) -> bool:
    """
    Check if the model supports prompt caching
    
    :param model_id: Model ID to check
    :return: True if the model supports caching, False otherwise
    """
    model_id = model_id.replace("us.","").replace("eu.","").replace("apac.","")

    result = model_id in CACHE_SUPPORTED_MODELS
    # Removed redundant print statement
    return result

def get_cache_config(model_id: str) -> dict:
    """
    Get cache configuration for the model
    
    :param model_id: Model ID
    :return: Cache configuration dictionary
    """
    model_id = model_id.replace("us.","").replace("eu.","").replace("apac.","")

    if model_id in CACHE_CONFIG:
        config = CACHE_CONFIG[model_id]
        print(f"[CACHE CONFIG] Cache config for model {model_id}: {config}")
        logger.info(f"[CACHE CONFIG] Cache config for model {model_id}: {config}")
        return config

    # Return default configuration if model not found
    default_config = {
        "min_tokens": 1024,
        "max_checkpoints": 4,
        "supported_fields": ["system", "messages"]
    }
    print(f"[CACHE CONFIG] Using default cache config for model {model_id}: {default_config}")
    logger.info(f"[CACHE CONFIG] Using default cache config for model {model_id}: {default_config}")
    return default_config

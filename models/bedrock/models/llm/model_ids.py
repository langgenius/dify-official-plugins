"""
Bedrock model IDs configuration file.
This file maintains the mapping between model names and their corresponding Bedrock model IDs.
Based on AWS documentation: 
- https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/models-regions.html
"""

BEDROCK_MODEL_IDS = {
    'anthropic claude': {
        'Claude 4.6 Sonnet': 'anthropic.claude-sonnet-4-6',
        'Claude 4.6 Opus': 'anthropic.claude-opus-4-6-v1',
        'Claude 4.5 Opus': 'anthropic.claude-opus-4-5-20251101-v1:0',
        'Claude 4.5 Haiku': 'anthropic.claude-haiku-4-5-20251001-v1:0',
        'Claude 4.5 Sonnet': 'anthropic.claude-sonnet-4-5-20250929-v1:0',
        'Claude 4.0 Sonnet': 'anthropic.claude-sonnet-4-20250514-v1:0',
        'Claude 4.0 Opus': 'anthropic.claude-opus-4-20250514-v1:0',
        'Claude 4.1 Opus': 'anthropic.claude-opus-4-1-20250805-v1:0',
        'Claude 3.7 Sonnet': 'anthropic.claude-3-7-sonnet-20250219-v1:0',
        'Claude 3.5 Sonnet': 'anthropic.claude-3-5-sonnet-20240620-v1:0',
        'Claude 3.5 Sonnet V2': 'anthropic.claude-3-5-sonnet-20241022-v2:0',
        'Claude 3.5 Haiku': 'anthropic.claude-3-5-haiku-20241022-v1:0',
        'Claude 3 Sonnet': 'anthropic.claude-3-sonnet-20240229-v1:0',
        'Claude 3 Haiku': 'anthropic.claude-3-haiku-20240307-v1:0',
        'Claude 3 Opus': 'anthropic.claude-3-opus-20240229-v1:0',
    },
    'amazon nova': {
        'Nova Pro V1': 'amazon.nova-pro-v1:0',
        'Nova Lite V1': 'amazon.nova-lite-v1:0',
        'Nova Lite V2': 'amazon.nova-2-lite-v1:0',
        'Nova Micro V1': 'amazon.nova-micro-v1:0',
        'Nova Premier V1': 'amazon.nova-premier-v1:0'
    },
    'meta': {
        'Llama 3 8B Instruct': 'meta.llama3-8b-instruct-v1:0',
        'Llama 3 70B Instruct': 'meta.llama3-70b-instruct-v1:0',
        'Llama 3.1 8B Instruct': 'meta.llama3-1-8b-instruct-v1:0',
        'Llama 3.1 70B Instruct': 'meta.llama3-1-70b-instruct-v1:0',
        'Llama 3.1 405B Instruct': 'meta.llama3-1-405b-instruct-v1:0',
        'Llama 3.2 11B Instruct': 'meta.llama3-2-11b-instruct-v1:0',
        'Llama 3.2 90B Instruct': 'meta.llama3-2-90b-instruct-v1:0'
    },
    'mistral': {
        'Mistral 7B Instruct': 'mistral.mistral-7b-instruct-v0:2',
        'Mistral Large': 'mistral.mistral-large-2402-v1:0',
        'Mistral Small': 'mistral.mistral-small-2402-v1:0',
        'Mixtral 8x7B Instruct': 'mistral.mixtral-8x7b-instruct-v0:1'
    },
    'ai21': {
        'Jamba 1.5 Mini': 'ai21.jamba-1-5-mini-v1:0',
        'Jamba 1.5 Large': 'ai21.jamba-1-5-large-v1:0'
    },
    'deepseek': {
        'DeepSeek R1': 'deepseek.r1-v1:0',
        'DeepSeek V3.1': 'deepseek.v3-v1:0'
    },
    'cohere': {
        'Command': 'cohere.command-text-v14',
        'Command Light': 'cohere.command-light-text-v14',
        'Command R': 'cohere.command-r-v1:0',
        'Command R+': 'cohere.command-r-plus-v1:0'
    },
    'qwen': {
        'Qwen3 235B': 'qwen.qwen3-235b-a22b-2507-v1:0',
        'Qwen3 32B': 'qwen.qwen3-32b-v1:0',
        'Qwen3 Coder 480B': 'qwen.qwen3-coder-480b-a35b-v1:0',
        'Qwen3 Coder 30B': 'qwen.qwen3-coder-30b-a3b-v1:0'
    },
    'openai': {
        'GPT OSS 120B': 'openai.gpt-oss-120b-1:0',
        'GPT OSS 20B': 'openai.gpt-oss-20b-1:0'
    }
}

def is_support_cross_region(model_id):
    unsupport_model_list = [
        "deepseek.v3-v1:0",
        "qwen.qwen3-235b-a22b-2507-v1:0",
        "qwen.qwen3-32b-v1:0",
        "qwen.qwen3-coder-480b-a35b-v1:0",
        "qwen.qwen3-coder-30b-a3b-v1:0",
        "openai.gpt-oss-120b-1:0",
        "openai.gpt-oss-20b-1:0"
    ]
    return model_id not in unsupport_model_list

def get_model_id(model_type, model_name):
    """
    Get the Bedrock model ID for the specified model type and name.
    
    Args:
        model_type (str): The type of model (e.g., 'claude', 'amazon nova')
        model_name (str): The name of the model (e.g., 'Claude 3 Opus')
        
    Returns:
        str: The corresponding Bedrock model ID, or None if not found
    """
    return BEDROCK_MODEL_IDS.get(model_type, {}).get(model_name)

def get_region_area(region_name, prefer_global=False):
    """
    Identify the geographic area based on AWS region name
    :param region_name: AWS region name, e.g., 'us-east-1'
    :param prefer_global: Whether to prefer global prefix (for models supporting global routing)
    :return: Geographic area, e.g., 'us', 'eu', 'apac', 'global'
    """
    if prefer_global:
        # For regions that support global prefix, prioritize returning global
        global_supported_regions = {
            'us-west-2', 'us-east-1', 'us-east-2', 
            'eu-west-1', 'ap-northeast-1'
        }
        if region_name in global_supported_regions:
            return 'global'
    
    prefix = region_name.split('-')[0].lower()

    area_mapping = {
        'us': 'us',
        'eu': 'eu',
        'ap': 'apac'
    }

    return area_mapping.get(prefix, None)

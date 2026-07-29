"""
Bedrock model IDs configuration file.
This file maintains the mapping between model names and their corresponding Bedrock model IDs.
Based on AWS documentation:
- https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html
- https://docs.aws.amazon.com/bedrock/latest/userguide/models-regions.html
"""

BEDROCK_MODEL_IDS = {
    'anthropic claude 5': {
        'Sonnet 5': 'anthropic.claude-sonnet-5',
        'Fable 5': 'anthropic.claude-fable-5',
    },
    'anthropic claude': {
        'Claude 4.8 Opus': 'anthropic.claude-opus-4-8',
        'Claude 4.7 Opus': 'anthropic.claude-opus-4-7',
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
        'DeepSeek V3.1': 'deepseek.v3-v1:0',
        'DeepSeek V3.2': 'deepseek.v3.2'
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
        'GPT-5.6 Sol': 'openai.gpt-5.6-sol',
        'GPT-5.6 Terra': 'openai.gpt-5.6-terra',
        'GPT-5.6 Luna': 'openai.gpt-5.6-luna',
        'GPT-5.5': 'openai.gpt-5.5',
        'GPT-5.4': 'openai.gpt-5.4',
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
        "openai.gpt-oss-20b-1:0",
        "openai.gpt-5.5",
        "openai.gpt-5.4",
        "openai.gpt-5.6-sol",
        "openai.gpt-5.6-terra",
        "openai.gpt-5.6-luna",
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


# Claude 5 generation models are invocable ONLY through inference profiles
# (inferenceTypesSupported == [INFERENCE_PROFILE]; live-verified — bare-ID
# converse returns ValidationException) and, unlike earlier Claude models,
# only 'us' and 'global' profiles exist — there are no eu./apac. geo
# profiles. See the model cards:
# https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html
# https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5.html
CLAUDE5_PROFILE_PREFIXES = {
    'anthropic.claude-sonnet-5': ('us', 'global'),
    'anthropic.claude-fable-5': ('us', 'global'),
}

CLAUDE5_REFUSAL_FALLBACK_BASE_ID = 'anthropic.claude-opus-4-8'

# All cross-region inference profile geo prefixes in use on Bedrock
# (jp./au. exist for Opus 4.7/4.8-era models).
_PROFILE_PREFIXES = ('global.', 'us.', 'eu.', 'apac.', 'jp.', 'au.')


def strip_profile_prefix(model_id):
    """Remove a leading cross-region profile prefix if present."""
    for prefix in _PROFILE_PREFIXES:
        if model_id.startswith(prefix):
            return model_id[len(prefix):]
    return model_id


def is_claude5_model(model_id):
    """True if model_id is a bare Claude 5 generation base model ID."""
    return model_id in CLAUDE5_PROFILE_PREFIXES


def is_claude5_profile_id(model_id):
    """True if model_id is a Claude 5 base ID, optionally profile-prefixed."""
    return strip_profile_prefix(model_id) in CLAUDE5_PROFILE_PREFIXES


def resolve_claude5_profile_id(model_id, cross_region, region_name):
    """
    Resolve the inference profile ID for a Claude 5 model.

    :param model_id: bare base model ID (e.g. 'anthropic.claude-sonnet-5')
    :param cross_region: 'global' or 'geographic'
    :param region_name: AWS region of the caller (e.g. 'us-east-1')
    :return: profile-prefixed model ID
    :raises ValueError: when the combination cannot be served, with a
        user-actionable message
    """
    # GovCloud is a separate AWS partition — commercial global./us. profile
    # IDs are not valid there.
    if region_name.startswith('us-gov-'):
        raise ValueError(
            f"{model_id} is not available in AWS GovCloud ({region_name}). "
            f"Claude 5 inference profiles exist only in commercial regions."
        )
    allowed = CLAUDE5_PROFILE_PREFIXES[model_id]
    if cross_region == 'global':
        # Claude 5 global profiles are available from virtually all commercial
        # regions — deliberately bypass the legacy get_region_area whitelist.
        return f"global.{model_id}"
    if cross_region == 'geographic':
        area = get_region_area(region_name)
        # The US geo profile serves Canadian source regions (per model card)
        if area is None and region_name.startswith('ca-'):
            area = 'us'
        if area in allowed:
            return f"{area}.{model_id}"
        raise ValueError(
            f"{model_id} has no '{area or region_name}' geographic inference profile. "
            f"From {region_name} this model supports only Global cross-region inference — "
            f"set Cross-Region Inference to 'global'."
        )
    raise ValueError(
        f"{model_id} can only be invoked through an inference profile. "
        f"Set Cross-Region Inference to 'global' (recommended) or 'geographic'."
    )


def get_claude5_fallback_model_id(profile_model_id):
    """
    Map a (possibly profile-prefixed) Claude 5 model ID to the Claude 4.8 Opus
    fallback ID with the same profile prefix.
    """
    base = strip_profile_prefix(profile_model_id)
    prefix = profile_model_id[: len(profile_model_id) - len(base)]
    return f"{prefix}{CLAUDE5_REFUSAL_FALLBACK_BASE_ID}"

"""
Bedrock rerank model IDs configuration file.
This file maintains the mapping between model names and their corresponding Bedrock model IDs.
Based on AWS documentation: 
- https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html
"""

BEDROCK_RERANK_MODEL_IDS = {
    'amazon': {
        'Amazon Rerank v1': 'amazon.rerank-v1:0',
    },
    'cohere': {
        'Cohere Rerank v3.5': 'cohere.rerank-v3-5:0',
    }
}

def get_model_id(model_type, model_name):
    """
    Get the Bedrock model ID for the specified model type and name.
    
    Args:
        model_type (str): The type of model (e.g., 'amazon', 'cohere')
        model_name (str): The name of the model (e.g., 'Amazon Rerank v1')
        
    Returns:
        str: The corresponding Bedrock model ID, or None if not found
    """
    return BEDROCK_RERANK_MODEL_IDS.get(model_type, {}).get(model_name)

def get_all_model_choices():
    """
    Get all available model choices for dropdown selection.
    
    Returns:
        list: List of tuples (model_type, model_name) for all available models
    """
    choices = []
    for model_type, models in BEDROCK_RERANK_MODEL_IDS.items():
        for model_name in models.keys():
            choices.append((model_type, model_name))
    return choices
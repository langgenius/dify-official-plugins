"""
Bedrock text embedding model IDs configuration file.
This file maintains the mapping between model names and their corresponding Bedrock model IDs.
Based on AWS documentation: 
- https://docs.aws.amazon.com/bedrock/latest/userguide/models-supported.html
"""

BEDROCK_TEXT_EMBEDDING_MODEL_IDS = {
    'amazon': {
        'Titan Embeddings G1 - Text': 'amazon.titan-embed-text-v1',
        'Titan Text Embeddings V2': 'amazon.titan-embed-text-v2:0',
    },
    'cohere': {
        'Embed English v3': 'cohere.embed-english-v3',
        'Embed Multilingual v3': 'cohere.embed-multilingual-v3',
    }
}

def get_model_id(model_type, model_name):
    """
    Get the Bedrock model ID for the specified model type and name.
    
    Args:
        model_type (str): The type of model (e.g., 'amazon', 'cohere')
        model_name (str): The name of the model (e.g., 'Titan Text Embeddings V2')
        
    Returns:
        str: The corresponding Bedrock model ID, or None if not found
    """
    return BEDROCK_TEXT_EMBEDDING_MODEL_IDS.get(model_type, {}).get(model_name)

def get_all_model_choices():
    """
    Get all available model choices for dropdown selection.
    
    Returns:
        list: List of tuples (model_type, model_name) for all available models
    """
    choices = []
    for model_type, models in BEDROCK_TEXT_EMBEDDING_MODEL_IDS.items():
        for model_name in models.keys():
            choices.append((model_type, model_name))
    return choices
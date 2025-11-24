"""
Test script for multimodalembedding@001 model
"""

from models.text_embedding.text_embedding import VertexAiTextEmbeddingModel
from dify_plugin.entities.model.text_embedding import MultiModalContent
from dify_plugin.entities.model import EmbeddingInputType

def test_multimodal_embedding():
    """
    Example of how to use multimodalembedding@001
    """
    # Initialize the model
    model = VertexAiTextEmbeddingModel()
    
    # Model configuration
    model_name = "multimodalembedding@001"
    
    # Credentials - you need to provide your actual credentials
    credentials = {
        "vertex_project_id": "your-project-id",
        "vertex_location": "us-central1",
        "vertex_service_account_key": "base64-encoded-service-account-key"  # Optional
    }
    
    # Example 1: Text-only embedding
    text_content = MultiModalContent(
        content="This is a sample text for embedding"
    )
    
    # Example 2: Text with image (multimodal)
    multimodal_content = MultiModalContent(
        content=[
            {"text": "This is an image of a cat"},
            {"image": {"url": "https://example.com/cat.jpg"}}  # Or base64 encoded image
        ]
    )
    
    # Example 3: Multiple text parts
    multi_text_content = MultiModalContent(
        content=[
            {"text": "First part of the text."},
            {"text": "Second part of the text."}
        ]
    )
    
    # Invoke the multimodal embedding model
    try:
        # For text-only
        result = model._invoke_multimodal(
            model=model_name,
            credentials=credentials,
            documents=[text_content],
            input_type=EmbeddingInputType.DOCUMENT
        )
        print(f"Text embedding result: {result.embeddings[0][:5]}...")  # Show first 5 dimensions
        print(f"Usage: {result.usage}")
        
        # For multimodal content
        result = model._invoke_multimodal(
            model=model_name,
            credentials=credentials,
            documents=[multimodal_content],
            input_type=EmbeddingInputType.DOCUMENT
        )
        print(f"Multimodal embedding result: {result.embeddings[0][:5]}...")
        print(f"Usage: {result.usage}")
        
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_multimodal_embedding()

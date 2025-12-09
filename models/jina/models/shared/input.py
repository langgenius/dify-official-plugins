from dify_plugin.entities.model.text_embedding import MultiModalContentType
from dify_plugin.interfaces.model.text_embedding_model import MultiModalContent


def transform_jina_input_text(model: str, text: str) -> dict:
    """
    Transform text input for Jina model

    :param model: model name
    :param text: input text
    :return: transformed input
    """
    specific_models = ["jina-clip-v1", "jina-clip-v2", "jina-embeddings-v4", "jina-reranker-m0"]

    if model in specific_models:
        # For specific models, wrap text in a dictionary
        return {"text": text}
    return text


def transform_jina_input_multi_modal(model: str, documents: list[MultiModalContent]) -> list[dict]:
    """
    Transform text input for Jina model

    :param model: model name
    :param text: input text
    :return: transformed input
    """
    specific_models = ["jina-clip-v1", "jina-clip-v2", "jina-embeddings-v4", "jina-reranker-m0"]

    if model not in specific_models:
        raise ValueError(f"Model {model} does not support multimodal embedding")
    inputs = []
    for document in documents:
        if document.content_type == MultiModalContentType.TEXT:
            inputs.append({"text": document.content})
        elif document.content_type == MultiModalContentType.IMAGE:
            inputs.append({"image": document.content})
        else:
            raise ValueError(f"Unsupported content type: {document.content_type}")
    return inputs

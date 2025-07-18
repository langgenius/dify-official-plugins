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
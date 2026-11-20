from models.text_embedding.text_embedding import OpenAITextEmbeddingModel


def _validate(url: str) -> str:
    model = OpenAITextEmbeddingModel(model_schemas=[])
    return model._validate_image_url(url)


def test_data_uri_is_allowed():
    assert _validate("data:image/png;base64,abc") == "data:image/png;base64,abc"


def test_public_http_url_is_allowed():
    assert _validate("https://example.com/image.png") == "https://example.com/image.png"


def test_localhost_is_blocked():
    assert _validate("http://localhost:8080/image.png") == ""
    assert _validate("http://127.0.0.1/image.png") == ""
    assert _validate("http://[::1]/image.png") == ""


def test_private_ip_is_blocked():
    assert _validate("http://10.0.0.5/image.png") == ""
    assert _validate("http://192.168.1.10/image.png") == ""


def test_non_http_schemes_are_blocked():
    assert _validate("file:///etc/passwd") == ""
    assert _validate("ftp://example.com/image.png") == ""


def test_empty_url_is_blocked():
    assert _validate("") == ""

import json
from unittest.mock import patch

import httpx2
import pytest
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.file.file import File
from provider.azure_openai_tool import AzureOpenAIProvider
from tools.image_edit import ImageEditTool
from tools.image_generate import ImageGenerateTool

CREDENTIALS = {
    "azure_openai_api_key": "test-key",
    "azure_openai_base_url": "https://example.openai.azure.com",
    "azure_openai_api_model_name": "my-deployment",
}


def response(request: httpx2.Request) -> httpx2.Response:
    return httpx2.Response(200, json={"created": 1, "data": [{"b64_json": "aW1hZ2U="}]})


@pytest.mark.parametrize(
    "version,path",
    [
        ("v1", "/openai/v1/images/generations"),
        ("2025-04-01-preview", "/openai/deployments/my-deployment/images/generations"),
    ],
)
def test_generate_routes_to_selected_azure_api(version, path):
    credentials = {**CREDENTIALS, "azure_openai_api_version": version}
    requests = []

    def capture(request):
        requests.append(request)
        return response(request)

    with (
        httpx2.Client(transport=httpx2.MockTransport(capture)) as transport,
        patch("openai._base_client.SyncHttpxClientWrapper", return_value=transport),
    ):
        tool = ImageGenerateTool.from_credentials(credentials)
        (result,) = list(
            tool.invoke({"prompt": "A blue square", "output_format": "jpeg"})
        )

    (request,) = requests
    assert request.url.path == path
    assert request.url.params["api-version"] == (
        "preview" if version == "v1" else version
    )
    assert request.headers["api-key"] == "test-key"
    assert "authorization" not in request.headers
    payload = json.loads(request.content)
    assert payload["model"] == "my-deployment"
    assert payload["output_format"] == "jpeg"
    assert result.type == ToolInvokeMessage.MessageType.BLOB


def test_edit_sends_deployment_in_v1_multipart_payload():
    requests = []

    def capture(request):
        requests.append(request)
        return response(request)

    with (
        httpx2.Client(transport=httpx2.MockTransport(capture)) as transport,
        patch("openai._base_client.SyncHttpxClientWrapper", return_value=transport),
        patch.object(
            File, "blob", new_callable=lambda: property(lambda self: b"image")
        ),
    ):
        image = File(
            type="image",
            filename="image.png",
            mime_type="image/png",
            url="https://example.com/image.png",
        )
        tool = ImageEditTool.from_credentials(CREDENTIALS)
        (result,) = list(tool.invoke({"prompt": "Draw a blue border", "image": image}))

    (request,) = requests
    assert request.url.path == "/openai/v1/images/edits"
    assert request.url.params["api-version"] == "preview"
    assert b'name="model"\r\n\r\nmy-deployment' in request.content
    assert b'name="image"; filename="image.png"' in request.content
    assert result.type == ToolInvokeMessage.MessageType.BLOB


def test_credential_validation_propagates_error_messages():
    error = ImageGenerateTool.from_credentials(CREDENTIALS).create_text_message(
        "Deployment not found"
    )
    with (
        patch.object(ImageGenerateTool, "invoke", return_value=iter([error])),
        pytest.raises(
            ToolProviderCredentialValidationError, match="Deployment not found"
        ),
    ):
        AzureOpenAIProvider()._validate_credentials(CREDENTIALS)

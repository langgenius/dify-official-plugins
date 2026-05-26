import base64
import os
import sys

import pytest
import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
PLUGIN_DIR = os.path.join(REPO_ROOT, "tools", "paddleocr")
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

from dify_plugin.file.file import File, FileType  # noqa: E402
from tools.document_parsing import DocumentParsingTool  # noqa: E402
from tools.document_parsing_vl import DocumentParsingVlTool  # noqa: E402
from tools.text_recognition import TextRecognitionTool  # noqa: E402
from tools.utils import normalize_file_input  # noqa: E402


def make_file(
    content: bytes,
    *,
    filename: str,
    mime_type: str | None,
    extension: str | None,
    file_type: FileType = FileType.DOCUMENT,
) -> File:
    file = File(
        url=f"https://example.com/files/{filename}",
        mime_type=mime_type,
        filename=filename,
        extension=extension,
        type=file_type,
    )
    file._blob = content
    return file


def test_file_upload_is_base64_encoded():
    file = make_file(
        b"image-bytes",
        filename="receipt.png",
        mime_type="image/png",
        extension=".png",
        file_type=FileType.IMAGE,
    )

    payload, normalized_file_type = normalize_file_input(file, "auto")

    assert payload == base64.b64encode(b"image-bytes").decode("utf-8")
    assert normalized_file_type == 1


def test_pdf_file_upload_infers_file_type():
    file = make_file(
        b"%PDF-1.7", filename="invoice.pdf", mime_type="application/pdf", extension=".pdf"
    )

    payload, normalized_file_type = normalize_file_input(file, "auto")

    assert payload == base64.b64encode(b"%PDF-1.7").decode("utf-8")
    assert normalized_file_type == 0


def test_image_file_upload_infers_file_type_from_filename_when_mime_type_missing():
    file = make_file(
        b"image-bytes",
        filename="scan.webp",
        mime_type=None,
        extension=None,
        file_type=FileType.IMAGE,
    )

    payload, normalized_file_type = normalize_file_input(file, None)

    assert payload == base64.b64encode(b"image-bytes").decode("utf-8")
    assert normalized_file_type == 1


def test_explicit_file_type_overrides_inference():
    file = make_file(
        b"image-bytes",
        filename="scan.png",
        mime_type="image/png",
        extension=".png",
        file_type=FileType.IMAGE,
    )

    payload, normalized_file_type = normalize_file_input(file, "pdf")

    assert payload == base64.b64encode(b"image-bytes").decode("utf-8")
    assert normalized_file_type == 0


def test_legacy_file_string_is_passed_through():
    payload, normalized_file_type = normalize_file_input("https://example.com/scan.pdf", "auto")

    assert payload == "https://example.com/scan.pdf"
    assert normalized_file_type is None


def test_missing_file_input_raises_clear_error():
    with pytest.raises(RuntimeError, match="File is not provided."):
        normalize_file_input(None, "auto")


def invoke_tool_with_mocked_api(monkeypatch, tool_cls, credentials, parameters):
    captured = {}
    module_name = tool_cls.__module__.split(".")[-1]

    def fake_api_request(api_url, params, access_token):
        captured["api_url"] = api_url
        captured["params"] = params
        captured["access_token"] = access_token
        return {
            "errorCode": 0,
            "result": {
                "ocrResults": [{"prunedResult": {"rec_texts": ["hello", "world"]}}],
                "layoutParsingResults": [{"markdown": {"text": "# Parsed", "images": {}}}],
            },
        }

    monkeypatch.setattr(f"tools.{module_name}.make_paddleocr_api_request", fake_api_request)
    tool = tool_cls.from_credentials(credentials)
    list(tool._invoke(parameters))
    return captured


def test_text_recognition_sends_normalized_file_to_api(monkeypatch):
    file = make_file(
        b"image-bytes",
        filename="receipt.png",
        mime_type="image/png",
        extension=".png",
        file_type=FileType.IMAGE,
    )

    captured = invoke_tool_with_mocked_api(
        monkeypatch,
        TextRecognitionTool,
        {
            "aistudio_access_token": "token",
            "text_recognition_api_url": "https://example.com/text-recognition",
        },
        {"file": file, "fileType": "auto", "visualize": False},
    )

    assert captured["api_url"] == "https://example.com/text-recognition"
    assert captured["access_token"] == "token"
    assert captured["params"]["file"] == base64.b64encode(b"image-bytes").decode("utf-8")
    assert captured["params"]["fileType"] == 1
    assert captured["params"]["visualize"] is False


def test_document_parsing_sends_normalized_file_to_api(monkeypatch):
    file = make_file(
        b"%PDF-1.7", filename="report.pdf", mime_type="application/pdf", extension=".pdf"
    )

    captured = invoke_tool_with_mocked_api(
        monkeypatch,
        DocumentParsingTool,
        {
            "aistudio_access_token": "token",
            "document_parsing_api_url": "https://example.com/document-parsing",
        },
        {"file": file, "fileType": "auto", "markdownIgnoreLabels": "header, footer"},
    )

    assert captured["api_url"] == "https://example.com/document-parsing"
    assert captured["params"]["file"] == base64.b64encode(b"%PDF-1.7").decode("utf-8")
    assert captured["params"]["fileType"] == 0
    assert captured["params"]["markdownIgnoreLabels"] == ["header", "footer"]


def test_document_parsing_vl_sends_normalized_file_to_api(monkeypatch):
    file = make_file(
        b"image-bytes",
        filename="scan.jpg",
        mime_type="image/jpeg",
        extension=".jpg",
        file_type=FileType.IMAGE,
    )

    captured = invoke_tool_with_mocked_api(
        monkeypatch,
        DocumentParsingVlTool,
        {
            "aistudio_access_token": "token",
            "document_parsing_vl_api_url": "https://example.com/document-parsing-vl",
        },
        {"file": file, "fileType": "auto", "promptLabel": "undefined"},
    )

    assert captured["api_url"] == "https://example.com/document-parsing-vl"
    assert captured["params"]["file"] == base64.b64encode(b"image-bytes").decode("utf-8")
    assert captured["params"]["fileType"] == 1
    assert "promptLabel" not in captured["params"]


def load_tool_yaml(tool_name: str) -> dict:
    path = os.path.join(PLUGIN_DIR, "tools", f"{tool_name}.yaml")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.mark.parametrize(
    "tool_name", ["text_recognition", "document_parsing", "document_parsing_vl"]
)
def test_yaml_exposes_single_file_parameter_as_uploaded_file(tool_name):
    tool_yaml = load_tool_yaml(tool_name)
    parameters = {parameter["name"]: parameter for parameter in tool_yaml["parameters"]}

    assert parameters["file"]["type"] == "file"
    assert parameters["file"]["required"] is True
    assert "file_upload" not in parameters
    assert "URL or base64" in parameters["file"]["human_description"]["en_US"]
    assert "Dify uploaded" in parameters["file"]["human_description"]["en_US"]

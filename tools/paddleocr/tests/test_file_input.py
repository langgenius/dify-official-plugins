import base64
import json
import os
import sys
from unittest.mock import MagicMock

import pytest
import yaml

PLUGIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PLUGIN_DIR not in sys.path:
    sys.path.insert(0, PLUGIN_DIR)

from dify_plugin.file.file import File, FileType  # noqa: E402
from tools.document_parsing import (  # noqa: E402
    DocumentParsingTool,
    build_pp_structure_v3_options,
)
from tools.document_parsing_vl import (  # noqa: E402
    DocumentParsingVlTool,
    build_paddleocr_vl_options,
)
from tools.text_recognition import TextRecognitionTool, build_ocr_options  # noqa: E402
from tools.utils import (  # noqa: E402
    DOCX_MIME_TYPE,
    _parse_doc_parsing_result,
    _submit_job,
    iter_docx_exports,
    normalize_file_input,
)


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

    input_value, is_temp_file, file_type_code = normalize_file_input(file, "auto")

    # New implementation saves to temp file for SDK
    assert os.path.exists(input_value)
    assert is_temp_file is True
    assert file_type_code == 1
    # Clean up
    os.unlink(input_value)


def test_pdf_file_upload_infers_file_type():
    file = make_file(
        b"%PDF-1.7",
        filename="invoice.pdf",
        mime_type="application/pdf",
        extension=".pdf",
    )

    input_value, is_temp_file, file_type_code = normalize_file_input(file, "auto")

    # New implementation saves to temp file for SDK
    assert os.path.exists(input_value)
    assert is_temp_file is True
    assert file_type_code == 0
    # Clean up
    os.unlink(input_value)


def test_image_file_upload_infers_file_type_from_filename_when_mime_type_missing():
    file = make_file(
        b"image-bytes",
        filename="scan.webp",
        mime_type=None,
        extension=None,
        file_type=FileType.IMAGE,
    )

    input_value, is_temp_file, file_type_code = normalize_file_input(file, None)

    # New implementation saves to temp file for SDK
    assert os.path.exists(input_value)
    assert is_temp_file is True
    assert file_type_code == 1
    # Clean up
    os.unlink(input_value)


def test_explicit_file_type_overrides_inference():
    file = make_file(
        b"image-bytes",
        filename="scan.png",
        mime_type="image/png",
        extension=".png",
        file_type=FileType.IMAGE,
    )

    input_value, is_temp_file, file_type_code = normalize_file_input(file, "pdf")

    # New implementation saves to temp file for SDK
    assert os.path.exists(input_value)
    assert is_temp_file is True
    assert file_type_code == 0
    # Clean up
    os.unlink(input_value)


def test_legacy_file_string_is_passed_through():
    input_value, is_temp_file, file_type_code = normalize_file_input(
        "https://example.com/scan.pdf", "auto"
    )

    assert input_value == "https://example.com/scan.pdf"
    assert is_temp_file is False
    assert file_type_code is None


def test_missing_file_input_raises_clear_error():
    with pytest.raises(RuntimeError, match="File is not provided."):
        normalize_file_input(None, "auto")


def test_option_builders_preserve_official_camel_case_keys():
    assert build_ocr_options(
        {
            "file": "ignored",
            "pageRanges": "ignored",
            "useDocUnwarping": True,
            "textRecScoreThresh": 0.5,
        }
    ) == {"useDocUnwarping": True, "textRecScoreThresh": 0.5}

    assert build_pp_structure_v3_options(
        {
            "markdownIgnoreLabels": "header, footer",
            "returnMarkdownImages": False,
            "outputFormats": "docx",
        }
    ) == {
        "markdownIgnoreLabels": ["header", "footer"],
        "returnMarkdownImages": False,
        "outputFormats": ["docx"],
    }

    assert build_paddleocr_vl_options(
        {
            "promptLabel": "undefined",
            "useLayoutDetection": True,
            "outputFormats": "none",
        }
    ) == {"useLayoutDetection": True}


def test_submit_url_sends_page_ranges_at_job_level(monkeypatch):
    response = MagicMock(status_code=200)
    response.json.return_value = {"data": {"jobId": "job-url"}}
    post = MagicMock(return_value=response)
    monkeypatch.setattr("requests.post", post)

    job_id = _submit_job(
        model="PP-OCRv6",
        file_url="https://example.com/report.pdf",
        file_path=None,
        options={"useDocUnwarping": True},
        base_url="https://paddle.example.com",
        headers={"Authorization": "Bearer token"},
        page_ranges=" 2,4-6 ",
    )

    assert job_id == "job-url"
    request_body = post.call_args.kwargs["json"]
    assert request_body["pageRanges"] == "2,4-6"
    assert request_body["optionalPayload"] == {"useDocUnwarping": True}
    assert "pageRanges" not in request_body["optionalPayload"]


def test_submit_file_sends_page_ranges_as_multipart_field(monkeypatch, tmp_path):
    input_file = tmp_path / "report.pdf"
    input_file.write_bytes(b"%PDF-1.7")
    response = MagicMock(status_code=200)
    response.json.return_value = {"data": {"jobId": "job-file"}}
    post = MagicMock(return_value=response)
    monkeypatch.setattr("requests.post", post)

    job_id = _submit_job(
        model="PP-StructureV3",
        file_url=None,
        file_path=str(input_file),
        options={"returnMarkdownImages": False},
        base_url="https://paddle.example.com",
        headers={"Authorization": "Bearer token"},
        page_ranges="1-3",
    )

    assert job_id == "job-file"
    request_data = post.call_args.kwargs["data"]
    assert request_data["pageRanges"] == "1-3"
    assert json.loads(request_data["optionalPayload"]) == {"returnMarkdownImages": False}


def test_document_result_parser_preserves_exports():
    encoded_docx = base64.b64encode(b"docx-bytes").decode()
    result = _parse_doc_parsing_result(
        "job-id",
        [
            {
                "result": {
                    "layoutParsingResults": [
                        {
                            "markdown": {"text": "# Parsed", "images": {}},
                            "outputImages": {},
                            "exports": {"docx": {"content": encoded_docx}},
                        }
                    ]
                }
            }
        ],
    )

    assert result["pages"][0]["exports"] == {"docx": {"content": encoded_docx}}


def test_docx_export_decodes_base64_content():
    result = {
        "pages": [{"exports": {"docx": {"content": base64.b64encode(b"docx-bytes").decode()}}}]
    }

    assert list(iter_docx_exports(result, filename_prefix="paddleocr-document")) == [
        ("paddleocr-document.docx", b"docx-bytes")
    ]


def test_docx_export_downloads_presigned_url(monkeypatch):
    response = MagicMock(content=b"downloaded-docx")
    get = MagicMock(return_value=response)
    monkeypatch.setattr("requests.get", get)
    result = {"pages": [{"exports": {"docx": {"content": "https://example.com/export.docx"}}}]}

    assert list(iter_docx_exports(result, filename_prefix="paddleocr-document")) == [
        ("paddleocr-document.docx", b"downloaded-docx")
    ]
    response.raise_for_status.assert_called_once_with()


def test_malformed_docx_export_warns_and_does_not_fail():
    warning_logger = MagicMock()
    result = {"pages": [{"exports": {"docx": {"content": "not-base64"}}}]}

    assert (
        list(
            iter_docx_exports(
                result,
                filename_prefix="paddleocr-document",
                warning_logger=warning_logger,
            )
        )
        == []
    )
    warning_logger.warning.assert_called_once()


def invoke_tool_with_mocked_api(
    monkeypatch,
    tool_cls,
    credentials,
    parameters,
    *,
    document_exports=None,
):
    captured = {}

    def fake_api_call(**kwargs):
        captured["kwargs"] = kwargs
        # Return mock result dict (HTTP API returns dict, not SDK objects)
        if tool_cls == TextRecognitionTool:
            return {
                "job_id": "test-job",
                "pages": [
                    {
                        "pruned_result": {"rec_texts": ["hello", "world"]},
                        "ocr_image_url": None,
                    }
                ],
            }
        else:
            return {
                "job_id": "test-job",
                "pages": [
                    {
                        "markdown_text": "# Parsed",
                        "markdown_images": {},
                        "output_images": {},
                        "exports": document_exports or {},
                    }
                ],
            }

    def fake_cleanup(*args):
        captured["cleanup"] = args

    # Mock the HTTP API call
    import tools.utils as utils_module

    monkeypatch.setattr(utils_module, "call_paddleocr_api", fake_api_call)
    monkeypatch.setattr(utils_module, "base64_to_temp_file", lambda *args: "temp_file.png")
    monkeypatch.setattr(utils_module, "cleanup_temp_file", fake_cleanup)

    # Mock in the specific tool module (they import these directly from utils)
    if tool_cls == TextRecognitionTool:
        import tools.text_recognition as tr_module

        monkeypatch.setattr(tr_module, "call_paddleocr_api", fake_api_call)
        monkeypatch.setattr(tr_module, "cleanup_temp_file", fake_cleanup)
    elif tool_cls == DocumentParsingTool:
        import tools.document_parsing as dp_module

        monkeypatch.setattr(dp_module, "call_paddleocr_api", fake_api_call)
        monkeypatch.setattr(dp_module, "cleanup_temp_file", fake_cleanup)
    else:
        import tools.document_parsing_vl as dpv_module

        monkeypatch.setattr(dpv_module, "call_paddleocr_api", fake_api_call)
        monkeypatch.setattr(dpv_module, "cleanup_temp_file", fake_cleanup)

    tool = tool_cls.from_credentials(credentials)
    messages = list(tool._invoke(parameters))
    return captured, messages


def test_text_recognition_sends_normalized_file_to_api(monkeypatch):
    file = make_file(
        b"image-bytes",
        filename="receipt.png",
        mime_type="image/png",
        extension=".png",
        file_type=FileType.IMAGE,
    )

    captured, _ = invoke_tool_with_mocked_api(
        monkeypatch,
        TextRecognitionTool,
        {
            "aistudio_access_token": "token",
        },
        {"file": file, "fileType": "auto"},
    )

    # HTTP API receives file_path (temp file), not base64 directly
    assert "file_path" in captured["kwargs"]
    assert captured["kwargs"]["file_path"] == "temp_file.png"
    assert captured["kwargs"]["model"] == "PP-OCRv5"
    assert captured["kwargs"]["is_document_parsing"] is False
    assert captured["cleanup"] == ("temp_file.png", True)


def test_document_parsing_sends_normalized_file_to_api(monkeypatch):
    file = make_file(
        b"%PDF-1.7",
        filename="report.pdf",
        mime_type="application/pdf",
        extension=".pdf",
    )

    captured, _ = invoke_tool_with_mocked_api(
        monkeypatch,
        DocumentParsingTool,
        {
            "aistudio_access_token": "token",
        },
        {
            "file": file,
            "fileType": "auto",
            "pageRanges": "2,4-6",
            "markdownIgnoreLabels": "header, footer",
            "returnMarkdownImages": False,
            "outputFormats": "docx",
        },
    )

    assert "file_path" in captured["kwargs"]
    assert captured["kwargs"]["file_path"] == "temp_file.png"
    assert captured["kwargs"]["model"] == "PP-StructureV3"
    assert captured["kwargs"]["is_document_parsing"] is True
    assert captured["kwargs"]["page_ranges"] == "2,4-6"
    assert captured["kwargs"]["options"] == {
        "markdownIgnoreLabels": ["header", "footer"],
        "returnMarkdownImages": False,
        "outputFormats": ["docx"],
    }


def test_document_parsing_vl_sends_normalized_file_to_api(monkeypatch):
    file = make_file(
        b"image-bytes",
        filename="scan.jpg",
        mime_type="image/jpeg",
        extension=".jpg",
        file_type=FileType.IMAGE,
    )

    captured, _ = invoke_tool_with_mocked_api(
        monkeypatch,
        DocumentParsingVlTool,
        {
            "aistudio_access_token": "token",
        },
        {
            "file": file,
            "fileType": "auto",
            "pageRanges": "1-3",
            "promptLabel": "undefined",
            "useLayoutDetection": True,
        },
    )

    assert "file_path" in captured["kwargs"]
    assert captured["kwargs"]["file_path"] == "temp_file.png"
    assert captured["kwargs"]["model"] == "PaddleOCR-VL-1.6"
    assert captured["kwargs"]["is_document_parsing"] is True
    assert captured["kwargs"]["page_ranges"] == "1-3"
    assert captured["kwargs"]["options"] == {"useLayoutDetection": True}


@pytest.mark.parametrize(
    ("tool_cls", "expected_filename"),
    [
        (DocumentParsingTool, "paddleocr-document.docx"),
        (DocumentParsingVlTool, "paddleocr-vl-document.docx"),
    ],
)
def test_document_tools_emit_docx_blob(monkeypatch, tool_cls, expected_filename):
    monkeypatch.setattr(
        tool_cls,
        "create_blob_message",
        lambda self, *, blob, meta: {"blob": blob, "meta": meta},
    )

    captured, messages = invoke_tool_with_mocked_api(
        monkeypatch,
        tool_cls,
        {"aistudio_access_token": "token"},
        {
            "file": "https://example.com/report.pdf",
            "fileType": "auto",
            "outputFormats": "docx",
        },
        document_exports={"docx": {"content": base64.b64encode(b"docx-bytes").decode()}},
    )

    blob_messages = [message for message in messages if isinstance(message, dict)]
    assert blob_messages == [
        {
            "blob": b"docx-bytes",
            "meta": {"filename": expected_filename, "mime_type": DOCX_MIME_TYPE},
        }
    ]
    assert captured["kwargs"]["options"]["outputFormats"] == ["docx"]


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


@pytest.mark.parametrize(
    "tool_name", ["text_recognition", "document_parsing", "document_parsing_vl"]
)
def test_yaml_exposes_pdf_page_ranges(tool_name):
    tool_yaml = load_tool_yaml(tool_name)
    parameters = {parameter["name"]: parameter for parameter in tool_yaml["parameters"]}

    assert parameters["pageRanges"]["type"] == "string"
    assert parameters["pageRanges"]["required"] is False


def test_text_recognition_yaml_exposes_all_official_models():
    tool_yaml = load_tool_yaml("text_recognition")
    parameters = {parameter["name"]: parameter for parameter in tool_yaml["parameters"]}
    model = parameters["model"]

    assert model["default"] == "PP-OCRv5"
    assert [option["value"] for option in model["options"]] == [
        "PP-OCRv5",
        "PP-OCRv5-latin",
        "PP-OCRv6",
    ]


@pytest.mark.parametrize("tool_name", ["document_parsing", "document_parsing_vl"])
def test_document_yaml_exposes_markdown_image_and_docx_controls(tool_name):
    tool_yaml = load_tool_yaml(tool_name)
    parameters = {parameter["name"]: parameter for parameter in tool_yaml["parameters"]}

    assert parameters["returnMarkdownImages"]["default"] is True
    assert parameters["outputFormats"]["default"] == "none"
    assert [option["value"] for option in parameters["outputFormats"]["options"]] == [
        "none",
        "docx",
    ]


def test_manifest_version_is_bumped():
    with open(os.path.join(PLUGIN_DIR, "manifest.yaml"), encoding="utf-8") as manifest_file:
        manifest = yaml.safe_load(manifest_file)

    assert manifest["version"] == "0.2.10"

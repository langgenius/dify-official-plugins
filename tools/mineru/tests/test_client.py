"""Contract tests for MinerU's V1 API and the legacy/cloud dispatch paths.

V1 fixtures follow the upstream HTTP API guide and api_server.py response models.
No document or credential leaves the test process.
"""

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.client import (
    API_LOCAL_V1,
    STATE_DONE,
    STATE_PENDING,
    STATE_RUNNING,
    CloudV4Client,
    Credentials,
    LocalLegacyClient,
    LocalV1Client,
    MineruAuthError,
    MineruError,
    MineruNetworkError,
    ParseOptions,
    make_client,
    validate_credentials,
)
from utils.results import from_v1_zip

HEALTH = {
    "status": "ok",
    "version": "4.0.10",
    "features": {
        "sources": ["file_id", "url", "inline"],
        "output_formats": ["markdown", "middle_json", "structured_content", "zip"],
    },
}


def response(status=200, body=None):
    result = requests.Response()
    result.status_code = status
    result._content = body if isinstance(body, bytes) else json.dumps(body).encode()
    return result


def credentials(base_url="https://mineru.example"):
    return Credentials.from_mapping(
        {
            "server_type": "local",
            "base_url": base_url,
            "token": "test-key",
            "gateway_header_name": "X-Gateway-Key",
            "gateway_header_value": "test-gateway-key",
        }
    )


@pytest.mark.parametrize(
    "base_url,root",
    [
        ("https://mineru.example", "https://mineru.example"),
        ("https://mineru.example/v1", "https://mineru.example"),
        ("https://mineru.example/v1/", "https://mineru.example"),
        (
            "https://mineru.example/proxy/mineru/v1/",
            "https://mineru.example/proxy/mineru",
        ),
        ("https://mineru.example/proxy/mineru", "https://mineru.example/proxy/mineru"),
    ],
)
def test_v1_base_url_and_credential_validation(base_url, root):
    with patch(
        "requests.request",
        side_effect=[response(body=HEALTH), response(body={"data": []})],
    ) as request:
        validate_credentials(credentials(base_url))
    assert [call.args[:2] for call in request.call_args_list] == [
        ("GET", root + "/v1/health"),
        ("GET", root + "/v1/files"),
    ]
    for call in request.call_args_list:
        assert call.kwargs["headers"]["Authorization"] == "Bearer test-key"
        assert call.kwargs["headers"]["X-Gateway-Key"] == "test-gateway-key"


@pytest.mark.parametrize("status", [404, 405])
def test_legacy_fallback_keeps_v2_form_parameters(status):
    with patch(
        "requests.request",
        side_effect=[
            response(status, {"detail": "Not Found"}),
            response(body={"results": {"document": {"md_content": "# Legacy"}}}),
        ],
    ) as request:
        client = make_client(credentials())
        assert isinstance(client, LocalLegacyClient)
        result = client.parse_file(
            "document.pdf",
            b"pdf",
            ParseOptions(
                language="en",
                enable_formula=False,
                enable_table=False,
                page_ranges="3-5",
            ),
            timeout=30,
        )
    call = request.call_args
    assert call.args == ("POST", "https://mineru.example/file_parse")
    assert call.kwargs["data"]["start_page_id"] == 2
    assert call.kwargs["data"]["end_page_id"] == 4
    assert call.kwargs["data"]["lang_list"] == ["en"]
    assert call.kwargs["data"]["formula_enable"] is False
    assert call.kwargs["data"]["table_enable"] is False
    assert result.state == STATE_DONE


@pytest.mark.parametrize(
    "status,body,error",
    [
        (401, {"detail": "Unauthorized"}, MineruAuthError),
        (403, {"detail": "Forbidden"}, MineruAuthError),
        (500, {"detail": "Internal server error"}, MineruNetworkError),
        (502, b"Bad Gateway", MineruNetworkError),
        (503, b"Service Unavailable", MineruNetworkError),
        (200, b"<html>WebUI</html>", MineruError),
        (200, {"status": "ok"}, MineruError),
        (307, b"", MineruError),
    ],
)
def test_health_errors_never_select_legacy_api(status, body, error):
    with patch("requests.request", return_value=response(status, body)) as request:
        with pytest.raises(error):
            make_client(credentials())
    assert request.call_count == 1
    assert request.call_args.args == ("GET", "https://mineru.example/v1/health")


def test_loading_v1_server_still_uses_v1():
    with patch(
        "requests.request",
        return_value=response(
            503, {"error": {"code": "model_not_ready", "message": "Loading models"}}
        ),
    ):
        assert isinstance(make_client(credentials()), LocalV1Client)


@pytest.mark.parametrize("token", ["", "wrong-key"])
def test_v1_rejects_missing_or_wrong_api_key(token):
    settings = credentials()
    settings.token = token
    with patch(
        "requests.request",
        side_effect=[
            response(body=HEALTH),
            response(
                401, {"error": {"code": "invalid_api_key", "message": "Invalid key"}}
            ),
        ],
    ):
        with pytest.raises(MineruAuthError, match="API key"):
            validate_credentials(settings)


@pytest.mark.parametrize("source", ["upload", "cached_upload", "url"])
def test_v1_parse_lifecycle_and_result_contract(source):
    root = "https://mineru.example/proxy"
    data = b"%PDF-1.4 test document"
    digest = hashlib.sha256(data).hexdigest()
    calls = []
    poll_count = 0

    def request(method, url, **kwargs):
        nonlocal poll_count
        assert url.startswith(root + "/v1/")
        path = url.removeprefix(root)
        calls.append((method, path))
        assert kwargs["headers"]["Authorization"] == "Bearer test-key"
        assert kwargs["headers"]["X-Gateway-Key"] == "test-gateway-key"
        if path == "/v1/health":
            return response(body=HEALTH)
        if path == "/v1/uploads":
            assert kwargs["json"] == {
                "filename": "document.pdf",
                "bytes": len(data),
                "mime_type": "application/pdf",
                "purpose": "parse",
                "sha256sum": digest,
            }
            if source == "cached_upload":
                return response(
                    body={
                        "id": "upload_1",
                        "status": "completed",
                        "file": {"id": "file-source"},
                    }
                )
            return response(
                body={
                    "id": "upload_1",
                    "status": "pending",
                    "upload_url": "/v1/uploads/upload_1/content",
                    "upload_method": "PUT",
                    "upload_headers": {"Content-Type": "application/pdf"},
                }
            )
        if path == "/v1/uploads/upload_1/content":
            assert method == "PUT"
            assert kwargs["data"] == data
            assert kwargs["headers"]["Content-Type"] == "application/pdf"
            return response(body={"status": "uploaded"})
        if path == "/v1/uploads/upload_1/complete":
            assert kwargs["json"]["sha256sum"] == digest
            return response(body={"status": "completed", "file": {"id": "file-source"}})
        if path == "/v1/parse/jobs":
            expected_source = (
                {"type": "url", "url": "https://files.example/document.pdf"}
                if source == "url"
                else {"type": "file_id", "file_id": "file-source"}
            )
            assert kwargs["json"] == {
                "files": [{"source": expected_source, "page_range": "2,4-6"}],
                "tier": "flash",
                "ocr_mode": "txt",
                "output_formats": ["zip"],
            }
            return response(202, {"job_id": "job_1", "status": "queued"})
        assert path == "/v1/parse/jobs/job_1"
        poll_count += 1
        if poll_count == 1:
            return response(
                body={
                    "job_id": "job_1",
                    "status": "running",
                    "progress": {"total": 1, "completed": 0},
                }
            )
        return response(
            body={
                "job_id": "job_1",
                "status": "completed",
                "files": [
                    {
                        "name": "document.pdf",
                        "status": "completed",
                        "output_files": {"zip": {"file_id": "file-output"}},
                    }
                ],
            }
        )

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("markdown.md", "# Parsed\n![Figure](images/figure.png)")
        output.writestr("structured_content.json", '[{"type":"text","text":"Parsed"}]')
        output.writestr("images/figure.png", b"image data")
    with (
        patch("requests.request", side_effect=request),
        patch(
            "requests.get", return_value=response(body=archive.getvalue())
        ) as download,
    ):
        client = make_client(credentials(root + "/v1"))
        options = ParseOptions(tier="flash", parse_method="txt", page_ranges="2,4-6")
        if source == "url":
            status = client.submit_url("https://files.example/document.pdf", options)
        else:
            status = client.submit_file("document.pdf", data, options)
        assert status.api == API_LOCAL_V1
        assert status.task_id == "job_1" and status.state == STATE_PENDING
        assert client.get_job(status.task_id).state == STATE_RUNNING
        status = client.get_job(status.task_id)
    assert status.state == STATE_DONE
    assert download.call_args.args[0] == root + "/v1/files/file-output/content"
    assert download.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"
    if source == "cached_upload":
        assert not any(path.endswith(("/content", "/complete")) for _, path in calls)
    document = from_v1_zip(status.zip_bytes, status.extra_files, "document.pdf")
    assert document.markdown.startswith("# Parsed")
    assert document.json_messages == [
        {"structured_content": [{"type": "text", "text": "Parsed"}]}
    ]
    assert document.images[0].name == "figure.png"


def test_cloud_keeps_existing_v4_api():
    settings = Credentials.from_mapping({"server_type": "remote", "token": "cloud-key"})
    with patch(
        "requests.request",
        return_value=response(body={"code": 0, "data": {"task_id": "cloud-task"}}),
    ) as request:
        client = make_client(settings)
        assert isinstance(client, CloudV4Client)
        assert (
            client.submit_url(
                "https://files.example/document.pdf", ParseOptions()
            ).task_id
            == "cloud-task"
        )
    assert request.call_count == 1
    assert request.call_args.args == ("POST", "https://mineru.net/api/v4/extract/task")

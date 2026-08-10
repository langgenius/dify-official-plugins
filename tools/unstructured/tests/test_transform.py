import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools import transform as transform_module
from tools.partition import PartitionTool
from tools.transform import (
    TransformTool,
    _MAX_RESULT_BYTES,
    _ensure_transfer_success,
    _get_job_results,
    _require_public_file_url,
    _require_public_https_transfer_url,
    _stages,
    _tool_payload,
    _validate_transform_tools,
    _validate_upload_size,
)


def _mcp_result(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(
        isError=False,
        structuredContent={"result": payload},
        content=[],
    )


def _install_transform_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    results: dict,
    download_chunks: tuple[bytes, ...] = (b"# Transformed document",),
    download_headers: dict[str, str] | None = None,
) -> tuple[list[tuple[str, dict]], list[tuple]]:
    tool_calls: list[tuple[str, dict]] = []
    transfers: list[tuple] = []
    statuses = iter(
        [
            {"status": "RUNNING", "poll_after": 1},
            {"status": "COMPLETED"},
        ]
    )

    class FakeDownloadResponse:
        def __init__(self, url: str) -> None:
            self.headers = download_headers or {}
            self.is_success = True
            self.request = httpx.Request("GET", url)
            self.status_code = 200

        async def aiter_bytes(self):
            for chunk in download_chunks:
                yield chunk

    class FakeHttpClient:
        def __init__(self, **options: object) -> None:
            if "follow_redirects" in options:
                assert options["follow_redirects"] is False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def put(
            self, url: str, *, headers: dict, content: bytes
        ) -> httpx.Response:
            transfers.append(("PUT", url, headers, content))
            return httpx.Response(200, request=httpx.Request("PUT", url))

        @asynccontextmanager
        async def stream(self, method: str, url: str):
            assert method == "GET"
            transfers.append(("GET", url))
            yield FakeDownloadResponse(url)

    class FakeSession:
        def __init__(self, *_: object, **__: object) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def initialize(self) -> None:
            return None

        async def call_tool(self, name: str, arguments: dict):
            tool_calls.append((name, arguments))
            if name == "request_file_upload_url":
                return _mcp_result(
                    {
                        "upload_url": "https://storage.example.com/upload?signature=secret",
                        "headers": {"x-upload-token": "token"},
                        "file_ref": "s3://input/document",
                    }
                )
            if name == "start_transform_job":
                return _mcp_result({"job_id": "job-123"})
            if name == "check_job_status":
                return _mcp_result(next(statuses))
            if name == "get_job_results":
                return _mcp_result(results)
            raise AssertionError(f"Unexpected MCP tool: {name}")

    @asynccontextmanager
    async def fake_streamable_http_client(*_: object, **__: object):
        yield object(), object(), None

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(transform_module.httpx, "AsyncClient", FakeHttpClient)
    monkeypatch.setattr(transform_module, "ClientSession", FakeSession)
    monkeypatch.setattr(
        transform_module, "streamable_http_client", fake_streamable_http_client
    )
    monkeypatch.setattr(transform_module.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(
        transform_module.socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (
                transform_module.socket.AF_INET,
                transform_module.socket.SOCK_STREAM,
                6,
                "",
                ("8.8.8.8", 443),
            )
        ],
    )
    return tool_calls, transfers


def test_builds_rag_stages() -> None:
    assert _stages(
        {
            "strategy": "hi_res",
            "languages": "eng, spa",
            "enrichments": "table_to_html, ner",
            "chunking_strategy": "chunk_by_title",
            "max_characters": 1200,
            "embed": True,
        }
    ) == {
        "partition": {"strategy": "hi_res", "languages": ["eng", "spa"]},
        "enrich": {"types": ["table_to_html", "ner"]},
        "chunk": {"strategy": "chunk_by_title", "max_characters": 1200},
        "embed": {},
    }


def test_unwraps_fastmcp_structured_result() -> None:
    result = SimpleNamespace(
        isError=False,
        structuredContent={"result": {"job_id": "job-123"}},
        content=[],
    )

    assert _tool_payload(result) == {"job_id": "job-123"}


def test_raises_transform_error_message() -> None:
    result = SimpleNamespace(
        isError=False,
        structuredContent={
            "result": {"error": {"code": "invalid_request", "message": "bad input"}}
        },
        content=[],
    )

    with pytest.raises(RuntimeError, match="bad input"):
        _tool_payload(result)


def test_requires_https_transform_url() -> None:
    with pytest.raises(ToolProviderCredentialValidationError, match="HTTPS"):
        TransformTool.validate_credentials(
            {
                "api_url": "http://mcp.transform.unstructured.io",
                "api_key": "secret",
            }
        )


def test_requires_hosted_transform_url() -> None:
    with pytest.raises(ToolProviderCredentialValidationError, match="hosted"):
        TransformTool.validate_credentials(
            {
                "api_url": "https://example.com",
                "api_key": "secret",
            }
        )


def test_validates_complete_transform_protocol() -> None:
    with pytest.raises(RuntimeError) as exc_info:
        _validate_transform_tools({"start_transform_job"})

    message = str(exc_info.value)
    assert "request_file_upload_url" in message
    assert "check_job_status" in message
    assert "get_job_results" in message


def test_rejects_files_over_transform_limit() -> None:
    _validate_upload_size(50 * 1024 * 1024)

    with pytest.raises(ValueError, match="50 MB"):
        _validate_upload_size(50 * 1024 * 1024 + 1)


@pytest.mark.parametrize("max_characters", [0, -1])
def test_rejects_non_positive_chunk_size(max_characters: int) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        _stages(
            {
                "chunking_strategy": "chunk_by_title",
                "max_characters": max_characters,
            }
        )


def test_rejects_private_transfer_destination() -> None:
    with pytest.raises(RuntimeError, match="public HTTPS"):
        asyncio.run(
            _require_public_https_transfer_url(
                "https://127.0.0.1/result?signature=secret",
                "Result download",
            )
        )


@pytest.mark.parametrize("operation", ["File upload", "Result download"])
def test_redacts_signed_transfer_url(operation: str) -> None:
    request = httpx.Request(
        "PUT", "https://storage.example.com/document?signature=top-secret"
    )
    response = httpx.Response(403, request=request)

    with pytest.raises(RuntimeError) as exc_info:
        _ensure_transfer_success(response, operation)

    message = str(exc_info.value)
    assert "https://storage.example.com/document" in message
    assert "signature" not in message
    assert "top-secret" not in message


def test_retries_results_until_materialized(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        SimpleNamespace(
            isError=False,
            structuredContent={
                "result": {
                    "error": {
                        "code": "job_not_complete",
                        "message": "results are not ready",
                    }
                }
            },
            content=[],
        ),
        SimpleNamespace(
            isError=False,
            structuredContent={"result": {"files": [{"content": "done"}]}},
            content=[],
        ),
    ]

    class FakeSession:
        async def call_tool(self, name: str, arguments: dict[str, str]):
            assert name == "get_job_results"
            assert arguments == {"job_id": "job-123", "output_format": "md"}
            return responses.pop(0)

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    async def run() -> dict:
        deadline = asyncio.get_running_loop().time() + 10
        return await _get_job_results(
            FakeSession(),
            job_id="job-123",
            output_format="md",
            deadline=deadline,
        )

    assert asyncio.run(run()) == {"files": [{"content": "done"}]}
    assert responses == []


def test_omits_base64_images_from_json_results() -> None:
    class FakeSession:
        async def call_tool(self, name: str, arguments: dict[str, str]):
            assert name == "get_job_results"
            assert arguments == {
                "job_id": "job-123",
                "output_format": "json",
                "image_base64": "none",
            }
            return _mcp_result({"files": [{"content": "[]"}]})

    async def run() -> dict:
        deadline = asyncio.get_running_loop().time() + 10
        return await _get_job_results(
            FakeSession(),
            job_id="job-123",
            output_format="json",
            deadline=deadline,
        )

    assert asyncio.run(run()) == {"files": [{"content": "[]"}]}


def test_orchestrates_local_file_transform(monkeypatch: pytest.MonkeyPatch) -> None:
    tool_calls, transfers = _install_transform_fakes(
        monkeypatch,
        results={
            "files": [
                {
                    "download_url": "https://storage.example.com/result?signature=secret",
                    "output_ref": "s3://output/document",
                }
            ]
        },
    )
    file = SimpleNamespace(
        filename="document.pdf",
        mime_type="application/pdf",
        blob=b"%PDF synthetic",
    )

    result = asyncio.run(
        TransformTool._transform(
            None,
            api_url="https://mcp.transform.unstructured.io",
            api_key="test-key",
            parameters={"file": file, "output_format": "md", "strategy": "auto"},
        )
    )

    assert [name for name, _ in tool_calls] == [
        "request_file_upload_url",
        "start_transform_job",
        "check_job_status",
        "check_job_status",
        "get_job_results",
    ]
    assert tool_calls[1][1] == {
        "file_refs": ["s3://input/document"],
        "stages": {"partition": {"strategy": "auto"}},
    }
    assert transfers == [
        (
            "PUT",
            "https://storage.example.com/upload?signature=secret",
            {"x-upload-token": "token"},
            b"%PDF synthetic",
        ),
        ("GET", "https://storage.example.com/result?signature=secret"),
    ]
    assert result == {
        "job_id": "job-123",
        "output_ref": "s3://output/document",
        "filename": "document.md",
        "mime_type": "text/markdown",
        "content": b"# Transformed document",
    }


def test_orchestrates_public_url_transform(monkeypatch: pytest.MonkeyPatch) -> None:
    tool_calls, transfers = _install_transform_fakes(
        monkeypatch,
        results={
            "files": [
                {
                    "content": "# URL document",
                    "output_ref": "s3://output/url-document",
                }
            ]
        },
    )

    result = asyncio.run(
        TransformTool._transform(
            None,
            api_url="https://mcp.transform.unstructured.io",
            api_key="test-key",
            parameters={
                "file_url": "https://example.com/reports/document.pdf",
                "output_format": "md",
            },
        )
    )

    assert [name for name, _ in tool_calls] == [
        "start_transform_job",
        "check_job_status",
        "check_job_status",
        "get_job_results",
    ]
    assert tool_calls[0][1] == {
        "file_refs": ["https://example.com/reports/document.pdf"],
        "stages": {},
    }
    assert transfers == []
    assert result["filename"] == "document.md"
    assert result["content"] == b"# URL document"
    assert result["output_ref"] == "s3://output/url-document"


@pytest.mark.parametrize(
    "file_url",
    [
        "https:///document.pdf",
        "http://127.0.0.1/document.pdf",
        "https://10.0.0.1/document.pdf",
        "https://user:password@example.com/document.pdf",
        "http://localhost/document.pdf",
    ],
)
def test_rejects_non_public_file_url(file_url: str) -> None:
    with pytest.raises(ValueError, match=r"public HTTP\(S\) URL"):
        _require_public_file_url(file_url)


def test_rejects_download_over_content_length_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_transform_fakes(
        monkeypatch,
        results={
            "files": [
                {
                    "download_url": "https://storage.example.com/result",
                    "output_ref": "s3://output/large-document",
                }
            ]
        },
        download_headers={"content-length": str(_MAX_RESULT_BYTES + 1)},
    )

    with pytest.raises(RuntimeError) as exc_info:
        asyncio.run(
            TransformTool._transform(
                None,
                api_url="https://mcp.transform.unstructured.io",
                api_key="test-key",
                parameters={
                    "file_url": "https://example.com/document.pdf",
                    "output_format": "md",
                },
            )
        )

    message = str(exc_info.value)
    assert "50 MB inline result limit" in message
    assert "job-123" in message
    assert "s3://output/large-document" in message


def test_rejects_download_that_streams_over_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(transform_module, "_MAX_RESULT_BYTES", 8)
    _install_transform_fakes(
        monkeypatch,
        results={
            "files": [
                {
                    "download_url": "https://storage.example.com/result",
                    "output_ref": "s3://output/large-document",
                }
            ]
        },
        download_chunks=(b"12345", b"6789"),
    )

    with pytest.raises(RuntimeError, match="inline result limit"):
        asyncio.run(
            TransformTool._transform(
                None,
                api_url="https://mcp.transform.unstructured.io",
                api_key="test-key",
                parameters={
                    "file_url": "https://example.com/document.pdf",
                    "output_format": "md",
                },
            )
        )


def test_rejects_oversized_inline_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(transform_module, "_MAX_RESULT_BYTES", 4)
    _install_transform_fakes(
        monkeypatch,
        results={
            "files": [
                {
                    "content": "12345",
                    "output_ref": "s3://output/large-document",
                }
            ]
        },
    )

    with pytest.raises(RuntimeError, match="inline result limit"):
        asyncio.run(
            TransformTool._transform(
                None,
                api_url="https://mcp.transform.unstructured.io",
                api_key="test-key",
                parameters={
                    "file_url": "https://example.com/document.pdf",
                    "output_format": "md",
                },
            )
        )


def test_partition_rejects_transform_credentials() -> None:
    tool = SimpleNamespace(
        runtime=SimpleNamespace(
            credentials={
                "api_url": "https://mcp.transform.unstructured.io",
                "api_key": "secret",
                "server_type": "transform",
            }
        )
    )

    with pytest.raises(ToolProviderCredentialValidationError, match="use Partition"):
        PartitionTool._get_credentials(tool)

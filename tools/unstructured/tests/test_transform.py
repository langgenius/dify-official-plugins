import asyncio
from types import SimpleNamespace

import httpx
import pytest
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from tools.partition import PartitionTool
from tools.transform import (
    TransformTool,
    _ensure_transfer_success,
    _get_transform_results,
    _stages,
    _tool_payload,
    _validate_transform_tools,
)


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


def test_validates_complete_transform_protocol() -> None:
    with pytest.raises(RuntimeError) as exc_info:
        _validate_transform_tools({"transform_files"})

    message = str(exc_info.value)
    assert "request_file_upload_url" in message
    assert "check_transform_status" in message
    assert "get_transform_results" in message


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
            assert name == "get_transform_results"
            assert arguments == {"job_id": "job-123", "output_format": "md"}
            return responses.pop(0)

    async def no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", no_sleep)

    async def run() -> dict:
        deadline = asyncio.get_running_loop().time() + 10
        return await _get_transform_results(
            FakeSession(),
            job_id="job-123",
            output_format="md",
            deadline=deadline,
        )

    assert asyncio.run(run()) == {"files": [{"content": "done"}]}
    assert responses == []


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

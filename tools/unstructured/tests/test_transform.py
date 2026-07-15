from types import SimpleNamespace

import pytest

from tools.transform import _stages, _tool_payload


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

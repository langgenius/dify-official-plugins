import pytest

from tools._mcp import clean_string_list, result_summary
from tools.web_fetch import build_fetch_arguments
from tools.web_search import build_search_arguments


def test_build_search_arguments_normalizes_queries() -> None:
    assert build_search_arguments(
        {
            "objective": "  current Dify release  ",
            "search_queries": [" dify release ", "docs"],
            "session_id": " session-123 ",
        }
    ) == {
        "objective": "current Dify release",
        "search_queries": ["dify release", "docs"],
        "session_id": "session-123",
    }


def test_build_fetch_arguments_omits_blank_optional_values() -> None:
    assert build_fetch_arguments(
        {
            "urls": [" https://example.com/a ", "https://example.com/b"],
            "objective": " ",
            "search_queries": [],
            "full_content": False,
        }
    ) == {"urls": ["https://example.com/a", "https://example.com/b"]}


def test_build_fetch_arguments_forwards_explicit_options() -> None:
    assert build_fetch_arguments(
        {
            "urls": "https://example.com",
            "objective": "exact wording",
            "search_queries": "example docs, exact wording",
            "full_content": True,
            "session_id": "session-123",
        }
    ) == {
        "urls": ["https://example.com"],
        "objective": "exact wording",
        "search_queries": ["example docs", "exact wording"],
        "full_content": True,
        "session_id": "session-123",
    }


def test_required_lists_reject_empty_values() -> None:
    with pytest.raises(ValueError, match="urls"):
        clean_string_list([], field="urls")


def test_fetch_limits_url_count_and_objective_length() -> None:
    with pytest.raises(ValueError, match="at most 20"):
        build_fetch_arguments({"urls": [f"https://example.com/{i}" for i in range(21)]})
    with pytest.raises(ValueError, match="at most 200"):
        build_fetch_arguments({"urls": ["https://example.com"], "objective": "x" * 201})


def test_result_summary_does_not_duplicate_excerpts() -> None:
    summary = result_summary(
        "web_search",
        {
            "results": [
                {
                    "title": "Example",
                    "url": "https://example.com",
                    "excerpts": ["long content"],
                }
            ]
        },
    )
    assert summary == "## Search results\n- [Example](https://example.com)"
    assert "long content" not in summary

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from requests import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datasources.crawl import build_crawl_payload
from datasources.firecrawl_app import FirecrawlApp
from provider.firecrawl_datasource import FirecrawlDatasourceProvider


def response(status_code: int, body: dict) -> Mock:
    result = Mock()
    result.status_code = status_code
    result.ok = 200 <= status_code < 400
    result.json.return_value = body
    result.text = str(body)
    return result


def test_build_crawl_payload_uses_v2_discovery_depth() -> None:
    payload = build_crawl_payload(
        {
            "crawl_subpages": True,
            "max_depth": 2,
            "limit": 10,
            "only_main_content": False,
        }
    )

    assert payload["maxDiscoveryDepth"] == 2
    assert "maxDepth" not in payload
    assert payload["limit"] == 10


def test_build_crawl_payload_omits_depth_when_subpages_are_disabled() -> None:
    payload = build_crawl_payload(
        {"crawl_subpages": False, "max_depth": 2, "limit": 10}
    )

    assert "maxDiscoveryDepth" not in payload
    assert payload["limit"] == 1


def test_crawl_lifecycle_uses_v2_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    request = Mock(
        side_effect=[
            response(
                200, {"success": True, "id": "job-id", "url": "https://example.com"}
            ),
            response(
                200, {"status": "scraping", "total": 1, "completed": 0, "data": []}
            ),
            response(200, {"status": "cancelled"}),
        ]
    )
    monkeypatch.setattr("datasources.firecrawl_app.requests.request", request)
    app = FirecrawlApp(api_key="fc-test")

    assert app.crawl_url("https://example.com", wait=False)["id"] == "job-id"
    assert app.check_crawl_status("job-id")["status"] == "scraping"
    assert app.cancel_crawl_job("job-id")["status"] == "cancelled"

    assert [call.args[:2] for call in request.call_args_list] == [
        ("POST", "https://api.firecrawl.dev/v2/crawl"),
        ("GET", "https://api.firecrawl.dev/v2/crawl/job-id"),
        ("DELETE", "https://api.firecrawl.dev/v2/crawl/job-id"),
    ]


def test_collects_v2_next_page(monkeypatch: pytest.MonkeyPatch) -> None:
    next_url = "https://api.firecrawl.dev/v2/crawl/job-id?skip=1"
    request = Mock(
        return_value=response(
            200,
            {
                "status": "completed",
                "total": 2,
                "completed": 2,
                "data": [
                    {
                        "markdown": "second",
                        "metadata": {"sourceURL": "https://example.com/second"},
                    }
                ],
            },
        )
    )
    monkeypatch.setattr("datasources.firecrawl_app.requests.request", request)
    app = FirecrawlApp(api_key="fc-test")

    result = app._collect_all_crawl_pages(
        {
            "status": "completed",
            "total": 2,
            "completed": 2,
            "next": next_url,
            "data": [
                {
                    "markdown": "first",
                    "metadata": {"sourceURL": "https://example.com/first"},
                }
            ],
        }
    )

    assert [item["content"] for item in result] == ["first", "second"]
    assert request.call_args.args[:2] == ("GET", next_url)


def test_failed_v2_status_preserves_error_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FirecrawlApp(api_key="fc-test")
    monkeypatch.setattr(
        app,
        "check_crawl_status",
        Mock(return_value={"status": "failed", "error": "crawl failed"}),
    )

    with pytest.raises(HTTPError, match="Job job-id failed: crawl failed"):
        app._monitor_job_status("job-id", poll_interval=0)


@pytest.mark.parametrize("status_code", [400, 401, 402])
def test_non_retryable_api_errors_preserve_firecrawl_message(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    request = Mock(
        return_value=response(status_code, {"success": False, "error": "bad request"})
    )
    monkeypatch.setattr("datasources.firecrawl_app.requests.request", request)
    app = FirecrawlApp(api_key="fc-test")

    with pytest.raises(HTTPError, match=rf"\({status_code}\): bad request"):
        app.crawl_url("https://example.com", wait=False)

    request.assert_called_once()


def test_rate_limit_response_is_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    request = Mock(
        side_effect=[
            response(429, {"success": False, "error": "rate limited"}),
            response(200, {"success": True, "id": "job-id"}),
        ]
    )
    monkeypatch.setattr("datasources.firecrawl_app.requests.request", request)
    monkeypatch.setattr("datasources.firecrawl_app.time.sleep", Mock())
    app = FirecrawlApp(api_key="fc-test")

    assert app.crawl_url("https://example.com", wait=False)["id"] == "job-id"
    assert request.call_count == 2


def test_credential_validation_uses_v2_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    post = Mock(return_value=response(200, {"success": True, "id": "job-id"}))
    monkeypatch.setattr("provider.firecrawl_datasource.requests.post", post)

    FirecrawlDatasourceProvider._validate_credentials(
        object(),
        {
            "firecrawl_api_key": "fc-test",
            "base_url": "https://api.firecrawl.dev/",
        },
    )

    assert post.call_args.args[0] == "https://api.firecrawl.dev/v2/crawl"


def test_credential_validation_preserves_v2_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    post = Mock(
        return_value=response(401, {"success": False, "error": "Invalid API key"})
    )
    monkeypatch.setattr("provider.firecrawl_datasource.requests.post", post)

    with pytest.raises(ToolProviderCredentialValidationError, match="Invalid API key"):
        FirecrawlDatasourceProvider._validate_credentials(
            object(), {"firecrawl_api_key": "fc-invalid"}
        )

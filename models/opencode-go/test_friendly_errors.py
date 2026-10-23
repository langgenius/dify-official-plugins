"""User-facing error mapping tests (quota / 5xx / auth / param)."""
from types import SimpleNamespace

from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from models.llm import friendly_errors


def _resp(status: int) -> SimpleNamespace:
    return SimpleNamespace(status_code=status)


def test_go_usage_limit_is_friendly() -> None:
    body = (
        '{"type":"error","error":{"type":"GoUsageLimitError",'
        '"message":"Go usage limit exceeded"},'
        '"metadata":{"workspace":"wrk_x","limitName":"5 hour"}}'
    )
    err = friendly_errors.map_http_error(429, body)
    assert isinstance(err, InvokeRateLimitError)
    text = str(err)
    assert "套餐用量已达上限" in text
    assert "5 小时" in text
    assert "升级套餐" in text
    # raw dump is reduced to a short technical tail
    assert "GoUsageLimitError" in text
    assert len(text) < 200


def test_server_error_is_friendly() -> None:
    err = friendly_errors.map_http_error(500, "upstream exploded")
    assert isinstance(err, InvokeServerUnavailableError)
    text = str(err)
    assert "暂时不可用" in text
    assert "稍后重试" in text


def test_auth_error_is_friendly() -> None:
    err = friendly_errors.map_http_error(401, '{"error":{"type":"authentication_error"}}')
    assert isinstance(err, InvokeAuthorizationError)
    assert "API Key" in str(err)


def test_param_error_is_friendly() -> None:
    body = (
        '{"error":{"param":"top_p must be within [0.01, 1.0]",'
        '"type":"server_error","message":"Param Incorrect"}}'
    )
    err = friendly_errors.map_http_error(400, body)
    assert isinstance(err, InvokeBadRequestError)
    text = str(err)
    assert "参数不合法" in text
    assert "top_p" in text


def test_generic_429_is_friendly() -> None:
    err = friendly_errors.map_http_error(429, "slow down")
    assert isinstance(err, InvokeRateLimitError)
    assert "限流" in str(err)


def test_region_block_is_friendly() -> None:
    err = friendly_errors.map_http_error(
        403, '{"error":{"type":"unsupported_country_region_territory"}}'
    )
    assert isinstance(err, InvokeAuthorizationError)
    assert "地区" in str(err)


def test_rewrite_oaicompat_invoke_error() -> None:
    raw = InvokeError(
        'API request failed with status code 429: {"type":"error",'
        '"error":{"type":"GoUsageLimitError","message":"Go usage limit exceeded"},'
        '"metadata":{"limitName":"day"}}'
    )
    err = friendly_errors.rewrite_invoke_error(raw)
    assert isinstance(err, InvokeRateLimitError)
    assert "套餐用量已达上限" in str(err)


def test_stream_error_uses_friendly_message() -> None:
    err = friendly_errors.wrap_stream_error(
        '{"type":"error","error":{"type":"GoUsageLimitError","message":"Go usage limit exceeded"}}'
    )
    assert isinstance(err, InvokeRateLimitError)
    assert "套餐" in str(err)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print("friendly_errors tests OK", len(tests))

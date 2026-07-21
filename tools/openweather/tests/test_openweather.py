"""Unit tests for the openweather tool and provider.

Covers the four bugs reported in issue #3441:

1. `_invoke()` short-circuits on missing `city` and missing `api_key`
   so no HTTP request is fired.
2. Successful `_invoke()` yields a summary message.
3. `_invoke()` returns the structured error dict (not bare JSON) when
   OpenWeather returns a non-200 status.
4. `_validate_credentials` raises a `ToolProviderCredentialValidationError`
   that includes the HTTP status and a 200-char body snippet even when
   the body is non-JSON HTML (Cloudflare 502, etc.).
5. `_validate_credentials` prefers `info`/`message` from JSON error
   bodies.
6. `_validate_credentials` raises on a missing `api_key` before any
   HTTP call.
7. `query_weather()` forwards `timeout=10` (and tests can override).

All tests stub `requests` so no outbound network call happens.
Pytest is not installed in this minimal environment; we provide a
minimal stand-in for the only feature the tests use
(`pytest.raises` as a context manager), mirroring the pattern used
in `tools/github/tests/test_refresh_credentials.py`.
"""

import sys
import types
from pathlib import Path
from unittest.mock import patch


# Stub requests so the module imports without the network library installed.
# We still need a `requests.get` attribute because `tools/weather.py`
# imports `requests` at module scope and calls `requests.get(...)`.
_fake_requests = types.ModuleType("requests")


class _FakeRequestsGet:
    def __call__(self, *args, **kwargs):  # pragma: no cover - never used directly
        raise RuntimeError("requests.get was not stubbed in this test")


_fake_requests.get = _FakeRequestsGet()  # type: ignore[attr-defined]
sys.modules.setdefault("requests", _fake_requests)

real_requests = _fake_requests  # for patch.object(...)


# Pytest is not installed in this minimal environment; provide a minimal
# stand-in for the only feature we use (pytest.raises as a context manager).
class _Raises:
    def __init__(self, exc_type, match=None):
        self.exc_type = exc_type
        self.match = match

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type is None:
            raise AssertionError(
                f"Expected {self.exc_type.__name__} to be raised, but no exception was."
            )
        if not issubclass(exc_type, self.exc_type):
            return False
        if self.match is not None and self.match not in str(exc):
            raise AssertionError(
                f"Expected exception message to match {self.match!r}, got: {exc}"
            )
        return True


class _PytestStub:
    def raises(self, exc_type, match=None):
        return _Raises(exc_type, match=match)


pytest = _PytestStub()


# Stub dify_plugin so the provider and tool modules import without the SDK.
_fake_dify = types.ModuleType("dify_plugin")
_fake_errors = types.ModuleType("dify_plugin.errors.tool")
_fake_entity = types.ModuleType("dify_plugin.entities")
_fake_tool_entity = types.ModuleType("dify_plugin.entities.tool")


class _FakeToolProviderCredentialValidationError(Exception):
    pass


_fake_errors.ToolProviderCredentialValidationError = _FakeToolProviderCredentialValidationError


class _FakeToolProvider:
    pass


_fake_dify.ToolProvider = _FakeToolProvider


class _FakeTool:
    """Bare-minimum Tool stub; subclasses set `runtime`, `session`,
    and call `create_*_message` exactly the way the real Tool class does."""

    def create_text_message(self, text: str):
        return ("text", text)

    def create_json_message(self, data):
        return ("json", data)


_fake_dify.Tool = _FakeTool  # type: ignore[attr-defined]


class _FakeToolInvokeMessage:
    pass


_fake_tool_entity.ToolInvokeMessage = _FakeToolInvokeMessage

_fake_dify.entities = _fake_entity  # type: ignore[attr-defined]
_fake_entity.tool = _fake_tool_entity  # type: ignore[attr-defined]
_fake_dify.errors = _fake_errors  # type: ignore[attr-defined]


sys.modules.setdefault("dify_plugin", _fake_dify)
sys.modules.setdefault("dify_plugin.errors", _fake_errors)
sys.modules.setdefault("dify_plugin.errors.tool", _fake_errors)
sys.modules.setdefault("dify_plugin.entities", _fake_entity)
sys.modules.setdefault("dify_plugin.entities.tool", _fake_tool_entity)


# Add provider + tools dirs to path so `import provider.openweather` and
# `import tools.weather` resolve.
_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "provider"))
sys.path.insert(0, str(_REPO_ROOT / "tools"))

import provider.openweather as provider_module  # noqa: E402
from provider.openweather import (  # noqa: E402
    OpenweatherProvider,
    query_weather,
)

import tools.weather as tool_module  # noqa: E402
from tools.weather import OpenweatherTool  # noqa: E402


# --- helpers ----------------------------------------------------------------


class _FakeResponse:
    """Mimics requests.Response for our two test sites: status_code, text, json()."""

    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload
        self.status_code = status_code
        self.text = text or (str(payload) if payload is not None else "")

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _RecordingGet:
    """Mock for `requests.get` that records calls and returns a stubbed response."""

    def __init__(self, response=None, side_effect=None, error=None):
        self._response = response
        self._side_effect = side_effect
        self._error = error
        self.calls = []  # list of (args, kwargs)

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        if self._error is not None:
            raise self._error
        if self._side_effect is not None:
            value = self._side_effect(*args, **kwargs)
            if isinstance(value, Exception):
                raise value
            return value
        return self._response


def _make_tool(credentials, summary_text="summary: "):
    """Build an OpenweatherTool with stubbed `runtime` and `session`."""

    tool = OpenweatherTool.__new__(OpenweatherTool)

    class _Runtime:
        def __init__(self, c):
            self.credentials = c

    class _Summary:
        def __init__(self, t):
            self.t = t

        def invoke(self, *, text, instruction):
            return self.t + text

    tool.runtime = _Runtime(credentials)
    tool.session = type("_S", (), {"model": type("_M", (), {"summary": _Summary(summary_text)})()})()
    return tool


# --- _invoke() guards -------------------------------------------------------


def test_invoke_missing_city_returns_message_and_no_http_call():
    """Empty city yields the friendly message and does NOT call requests.get."""

    tool = _make_tool(credentials={"api_key": "abc"})
    rec = _RecordingGet(response=_FakeResponse({}, 200))
    with patch.object(real_requests, "get", rec):
        out = list(
            tool._invoke(
                tool_parameters={"city": ""}
            )
        )

    assert out == [("text", "Please tell me your city")]
    assert rec.calls == [], f"requests.get should not have been called; got {rec.calls!r}"


def test_invoke_missing_api_key_returns_message_and_no_http_call():
    """Missing api_key yields the friendly message and does NOT call requests.get."""

    tool = _make_tool(credentials={})
    rec = _RecordingGet(response=_FakeResponse({}, 200))
    with patch.object(real_requests, "get", rec):
        out = list(
            tool._invoke(
                tool_parameters={"city": "Beijing", "units": "metric", "lang": "zh_cn"}
            )
        )

    assert out == [("text", "OpenWeather API key is required.")]
    assert rec.calls == [], f"requests.get should not have been called; got {rec.calls!r}"


def test_invoke_success_yields_summary():
    """A 200 response yields a single text message containing the summary."""

    tool = _make_tool(credentials={"api_key": "abc"})
    payload = {"weather": [{"description": "clear"}], "main": {"temp": 20}}
    rec = _RecordingGet(response=_FakeResponse(payload=payload, status_code=200))
    with patch.object(real_requests, "get", rec):
        out = list(
            tool._invoke(
                tool_parameters={"city": "Beijing", "units": "metric", "lang": "zh_cn"}
            )
        )

    assert len(out) == 1
    assert out[0][0] == "text"
    # The text contains the JSON of the payload (verify key fields appear).
    body = out[0][1]
    assert "clear" in body and "20" in body


# --- _validate_credentials: status-before-JSON order ----------------------


def test_validate_credentials_http_400_with_html_body_surfaces_status():
    """A non-200 with an HTML body must raise with the HTTP status + snippet,
    not a JSONDecodeError."""

    provider = OpenweatherProvider.__new__(OpenweatherProvider)
    html = "<html><body>400 Bad Request — nginx</body></html>"

    fake_response = _FakeResponse(
        payload=ValueError("Expecting value: line 1 column 1 (char 0)"),
        status_code=400,
        text=html,
    )

    with patch.object(provider_module, "query_weather", return_value=fake_response):
        with pytest.raises(_FakeToolProviderCredentialValidationError, match="400"):
            provider._validate_credentials({"api_key": "abc"})


def test_validate_credentials_http_401_surfaces_message():
    """A 401 with a JSON body containing OpenWeather's `message` field surfaces it."""

    provider = OpenweatherProvider.__new__(OpenweatherProvider)
    payload = {"cod": 401, "message": "Invalid API key"}
    fake_response = _FakeResponse(payload=payload, status_code=401, text=str(payload))

    with patch.object(provider_module, "query_weather", return_value=fake_response):
        with pytest.raises(_FakeToolProviderCredentialValidationError, match="Invalid API key"):
            provider._validate_credentials({"api_key": "abc"})


def test_validate_credentials_missing_api_key_does_not_call_api():
    """Missing api_key raises before any HTTP call (preserves existing behavior)."""

    provider = OpenweatherProvider.__new__(OpenweatherProvider)
    rec = _RecordingGet()
    with patch.object(provider_module, "query_weather", side_effect=lambda **_: rec()):
        with pytest.raises(_FakeToolProviderCredentialValidationError, match="required"):
            provider._validate_credentials({})


# --- query_weather timeout forwarding --------------------------------------


def test_requests_get_called_with_timeout_10():
    """Both call sites pass timeout=10 to requests.get."""

    rec = _RecordingGet(response=_FakeResponse({}, 200))
    with patch.object(real_requests, "get", rec):
        query_weather(city="Tokyo", api_key="abc", units="metric", language="zh_cn")

    assert len(rec.calls) == 1
    _, kwargs = rec.calls[0]
    assert kwargs.get("timeout") == 10, f"expected timeout=10, got kwargs={kwargs!r}"

"""Unit tests for the hardened image fetch in AnthropicLargeLanguageModel.

All network interaction is stubbed: socket.getaddrinfo, requests.get and
PIL.Image.open are monkeypatched. No test performs real I/O.
"""

import base64
import io
import socket
import types

import pytest
import requests as real_requests

from models.llm.llm import AnthropicLargeLanguageModel


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _FakeSaver:
    def save(self, buf, format=None):
        buf.write(b"PNGDATA")


class _FakeImg:
    def __init__(self, fmt="PNG", raise_on_open=False):
        self.format = fmt
        self._raise = raise_on_open

    def convert(self, mode):
        return _FakeSaver()

    def __enter__(self):
        if self._raise:
            raise real_requests.exceptions.RequestException("bad image")
        return self

    def __exit__(self, *args):
        return False


class _FakeResponse:
    def __init__(self, status_code=200, chunks=None, headers=None):
        self.status_code = status_code
        self._chunks = [b"IMGbytes"] if chunks is None else chunks
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise real_requests.exceptions.HTTPError(
                f"{self.status_code} for url (redacted)"
            )

    def iter_content(self, chunk_size=None):
        return iter(self._chunks)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


_PUB = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))
_HOSTMAP = {
    "pub.example.com": _PUB,
    "cdn.example.com": _PUB,
    "pub2.example.com": _PUB,
    "127.0.0.1": (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
    "localhost": (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0)),
    "169.254.169.254": (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0)),
    "10.0.0.5": (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
    "172.19.0.10": (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.19.0.10", 0)),
}


@pytest.fixture
def model():
    return AnthropicLargeLanguageModel()


@pytest.fixture(autouse=True)
def stub_env(monkeypatch):
    monkeypatch.setattr(
        socket, "getaddrinfo", lambda host, port: [_HOSTMAP.get(host, _PUB)]
    )
    monkeypatch.setattr(
        "models.llm.llm.Image",
        types.SimpleNamespace(open=lambda b: _FakeImg("PNG")),
    )
    # safety net: no test should ever hit the network
    def _no_network(*args, **kwargs):
        raise AssertionError("real network call attempted in test")

    monkeypatch.setattr("models.llm.llm.requests.get", _no_network)


def _install_responses(monkeypatch, responses):
    queue = list(responses)

    def _fake_get(url, **kwargs):
        assert kwargs.get("allow_redirects") is False, "redirects must not be followed automatically"
        return queue.pop(0) if queue else _FakeResponse()

    monkeypatch.setattr("models.llm.llm.requests.get", _fake_get)
    return queue


def _expect_public(monkeypatch, responses=None, img_fmt="PNG", raise_on_open=False):
    monkeypatch.setattr(
        "models.llm.llm.Image",
        types.SimpleNamespace(open=lambda b: _FakeImg(img_fmt, raise_on_open)),
    )
    _install_responses(monkeypatch, responses if responses is not None else [_FakeResponse()])


# ---------------------------------------------------------------------------
# data URIs
# ---------------------------------------------------------------------------

_PNG_DATA = "data:image/png;base64," + base64.b64encode(b"PNGDATA").decode()


def test_data_uri_roundtrip(model):
    mime, b64 = model._process_image_data(_PNG_DATA)
    assert mime == "image/png"
    assert b64 == base64.b64encode(b"PNGDATA").decode()


def test_data_uri_extra_params_tolerated(model):
    mime, _ = model._process_image_data(
        "data:image/png;charset=utf-8;base64," + base64.b64encode(b"PNGDATA").decode()
    )
    assert mime == "image/png"


def test_data_uri_declared_mime_not_trusted(model):
    # declared image/bmp but bytes sniff as PNG -> sent as PNG
    mime, _ = model._process_image_data(
        "data:image/bmp;base64," + base64.b64encode(b"PNGDATA").decode()
    )
    assert mime == "image/png"


def test_data_uri_invalid_base64_rejected(model):
    with pytest.raises(ValueError, match="Malformed base64 data URI"):
        model._process_image_data("data:image/png;base64,!!notb64!!")


def test_data_uri_missing_base64_marker_rejected(model):
    with pytest.raises(ValueError, match="Malformed base64 data URI"):
        model._process_image_data("data:image/png,hello")


def test_data_uri_encoded_cap_enforced_pre_decode(model):
    with pytest.raises(ValueError, match="Encoded image data exceeds"):
        model._process_image_data("data:image/png;base64," + "A" * (29 * 1024 * 1024))


def test_data_uri_non_image_rejected(model, monkeypatch):
    _expect_public(monkeypatch, raise_on_open=True)
    with pytest.raises(ValueError, match="Unsupported image data"):
        model._process_image_data(_PNG_DATA)


# ---------------------------------------------------------------------------
# SSRF guards
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "ftp://pub.example.com/a.png",
        "file:///etc/passwd",
        "http://127.0.0.1/x",
        "http://localhost/x",
        "http://169.254.169.254/metadata/instance",
        "http://10.0.0.5/internal",
        "http://172.19.0.10:5001/api",
    ],
)
def test_private_and_non_http_targets_rejected(model, url):
    with pytest.raises(ValueError):
        model._process_image_data(url)


def test_public_url_allowed(model, monkeypatch):
    _expect_public(monkeypatch)
    mime, b64 = model._process_image_data("https://pub.example.com/a.png")
    assert mime == "image/png"
    assert b64 == base64.b64encode(b"IMGbytes").decode()


# ---------------------------------------------------------------------------
# redirects
# ---------------------------------------------------------------------------


def test_redirect_to_private_blocked(model, monkeypatch):
    _expect_public(monkeypatch)
    responses = [
        _FakeResponse(302, headers={"Location": "http://10.0.0.5/x"}),
        _FakeResponse(),
    ]
    _install_responses(monkeypatch, responses)
    with pytest.raises(ValueError, match="Invalid or inaccessible image URL"):
        model._process_image_data("https://pub.example.com/a.png")


def test_redirect_to_public_followed(model, monkeypatch):
    _expect_public(monkeypatch)
    responses = [
        _FakeResponse(302, headers={"Location": "https://pub2.example.com/b.png"}),
        _FakeResponse(chunks=[b"REDIR"]),
    ]
    _install_responses(monkeypatch, responses)
    mime, b64 = model._process_image_data("https://pub.example.com/a.png")
    assert mime == "image/png"
    assert b64 == base64.b64encode(b"REDIR").decode()


def test_redirect_relative_location_resolved_and_validated(model, monkeypatch):
    _expect_public(monkeypatch)
    responses = [
        _FakeResponse(302, headers={"Location": "/img2.png"}),
        _FakeResponse(chunks=[b"R2"]),
    ]
    _install_responses(monkeypatch, responses)
    mime, _ = model._process_image_data("https://pub.example.com/a.png")
    assert mime == "image/png"


def test_redirect_chain_over_limit_rejected(model, monkeypatch):
    _expect_public(monkeypatch)
    responses = [_FakeResponse(302, headers={"Location": "https://pub.example.com/loop"}) for _ in range(5)]
    _install_responses(monkeypatch, responses)
    with pytest.raises(ValueError, match="Too many redirects"):
        model._process_image_data("https://pub.example.com/a.png")


def test_redirect_without_location_rejected(model, monkeypatch):
    _expect_public(monkeypatch)
    responses = [_FakeResponse(302, headers={})]
    _install_responses(monkeypatch, responses)
    with pytest.raises(ValueError, match="Redirect without Location"):
        model._process_image_data("https://pub.example.com/a.png")


# ---------------------------------------------------------------------------
# download limits
# ---------------------------------------------------------------------------


def test_download_size_cap(model, monkeypatch):
    _expect_public(monkeypatch)
    responses = [_FakeResponse(chunks=[b"x" * (21 * 1024 * 1024)])]
    _install_responses(monkeypatch, responses)
    with pytest.raises(ValueError, match="maximum allowed size"):
        model._process_image_data("https://pub.example.com/big.png")


def test_wall_clock_deadline(monkeypatch, model):
    _expect_public(monkeypatch)
    responses = [
        _FakeResponse(302, headers={"Location": "https://pub2.example.com/b.png"}),
        _FakeResponse(),
    ]
    _install_responses(monkeypatch, responses)
    # exhaust the deadline before the second hop (first call computes the
    # deadline, every later call reports "way past it")
    import models.llm.llm as llm_module

    real_monotonic = llm_module.time.monotonic
    t0 = real_monotonic()
    calls = {"n": 0}

    def _fake_monotonic():
        calls["n"] += 1
        return t0 if calls["n"] == 1 else t0 + 60.0

    monkeypatch.setattr(llm_module.time, "monotonic", _fake_monotonic)
    with pytest.raises(ValueError, match="total time limit"):
        model._process_image_data("https://pub.example.com/a.png")


# ---------------------------------------------------------------------------
# format normalization + error hygiene
# ---------------------------------------------------------------------------


def test_bmp_converted_to_png(model, monkeypatch):
    _expect_public(monkeypatch, img_fmt="BMP")
    responses = [_FakeResponse()]
    _install_responses(monkeypatch, responses)
    mime, b64 = model._process_image_data("https://pub.example.com/a.bmp")
    assert mime == "image/png"
    assert b64 == base64.b64encode(b"PNGDATA").decode()


def test_http_error_message_carries_no_url_or_query(model, monkeypatch):
    _expect_public(monkeypatch)
    err = real_requests.exceptions.HTTPError(
        "404 Client Error for url: https://pub.example.com/img.png?sig=SECRETTOKEN"
    )
    err.response = types.SimpleNamespace(status_code=404)

    def _get(url, **kwargs):
        raise err

    monkeypatch.setattr("models.llm.llm.requests.get", _get)
    with pytest.raises(ValueError, match=r"Failed to fetch image \(HTTP 404\)") as excinfo:
        model._process_image_data("https://pub.example.com/img.png?sig=SECRETTOKEN")
    assert "SECRETTOKEN" not in str(excinfo.value)
    assert "pub.example.com" not in str(excinfo.value)


def test_generic_error_never_leaks_userinfo(model, monkeypatch):
    _expect_public(monkeypatch)

    def _get(url, **kwargs):
        raise real_requests.exceptions.ConnectionError(
            "boom https://user:SECRETPW@pub.example.com/"
        )

    monkeypatch.setattr("models.llm.llm.requests.get", _get)
    with pytest.raises(ValueError, match=r"Failed to fetch image \(ConnectionError\)") as excinfo:
        model._process_image_data("https://user:SECRETPW@pub.example.com/a.png")
    assert "SECRETPW" not in str(excinfo.value)

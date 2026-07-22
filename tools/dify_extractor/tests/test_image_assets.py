from types import SimpleNamespace

import pytest
import requests
from dify_plugin.invocations.file import UploadFileResponse

from tools import image_assets
from tools.image_assets import ImageAssetService


class _Response:
    def __init__(self, content=b"image", headers=None, url="https://example.com/image.png"):
        self.content = content
        self.headers = headers or {"Content-Type": "image/png"}
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def raise_for_status(self):
        return None

    def iter_content(self, chunk_size):
        del chunk_size
        yield self.content


class _Uploader:
    def __init__(self, *, fail=False, preview_url="https://dify.example/preview.png"):
        self.fail = fail
        self.preview_url = preview_url
        self.calls = []

    def upload(self, filename, content, mime_type):
        self.calls.append((filename, content, mime_type))
        if self.fail:
            raise RuntimeError("upload failed")
        return UploadFileResponse(
            id="file-1",
            name=filename,
            size=len(content),
            extension=filename.rsplit(".", 1)[-1],
            mime_type=mime_type,
            preview_url=self.preview_url,
        )


def _service(uploader=None):
    uploader = uploader or _Uploader()
    tool = SimpleNamespace(session=SimpleNamespace(file=uploader))
    return ImageAssetService(tool), uploader


def test_remote_image_is_streamed_and_uploaded_with_one_dot(monkeypatch):
    service, uploader = _service()
    monkeypatch.setattr(image_assets.requests, "get", lambda *args, **kwargs: _Response())

    asset = service.download_and_upload("https://example.com/image.png")

    assert asset is not None
    filename, content, mime_type = uploader.calls[0]
    assert "..png" not in filename
    assert filename.endswith(".png")
    assert content == b"image"
    assert mime_type == "image/png"


def test_unsupported_url_scheme_is_skipped_without_request(monkeypatch):
    service, uploader = _service()

    def unexpected_request(*_args, **_kwargs):
        raise AssertionError("request should not run")

    monkeypatch.setattr(image_assets.requests, "get", unexpected_request)

    assert service.download_and_upload("file:///etc/passwd") is None
    assert uploader.calls == []


def test_remote_timeout_is_non_fatal(monkeypatch):
    service, uploader = _service()

    def timeout(*_args, **_kwargs):
        raise requests.Timeout("slow")

    monkeypatch.setattr(image_assets.requests, "get", timeout)

    assert service.download_and_upload("https://example.com/image.png") is None
    assert uploader.calls == []


def test_non_image_response_is_skipped(monkeypatch):
    service, uploader = _service()
    monkeypatch.setattr(
        image_assets.requests,
        "get",
        lambda *args, **kwargs: _Response(
            headers={"Content-Type": "text/html"},
            url="https://example.com/page",
        ),
    )

    assert service.download_and_upload("https://example.com/page") is None
    assert uploader.calls == []


@pytest.mark.parametrize("include_content_length", [True, False])
def test_remote_size_limit_with_and_without_content_length(monkeypatch, include_content_length):
    service, uploader = _service()
    monkeypatch.setattr(image_assets, "MAX_IMAGE_BYTES", 4)
    headers = {"Content-Type": "image/png"}
    if include_content_length:
        headers["Content-Length"] = "5"
    monkeypatch.setattr(
        image_assets.requests,
        "get",
        lambda *args, **kwargs: _Response(content=b"12345", headers=headers),
    )

    assert service.download_and_upload("https://example.com/image.png") is None
    assert uploader.calls == []


def test_image_count_limit_applies_to_embedded_images(monkeypatch):
    service, uploader = _service()
    monkeypatch.setattr(image_assets, "MAX_IMAGES", 1)

    assert service.upload_embedded(b"one", extension="png") is not None
    assert service.upload_embedded(b"two", extension="png") is None
    assert len(uploader.calls) == 1


def test_cumulative_budget_applies_to_embedded_images(monkeypatch):
    service, uploader = _service()
    monkeypatch.setattr(image_assets, "MAX_TOTAL_IMAGE_BYTES", 3)

    assert service.upload_embedded(b"12", extension="png") is not None
    assert service.upload_embedded(b"34", extension="png") is None
    assert len(uploader.calls) == 1


def test_failed_upload_still_consumes_cumulative_budget(monkeypatch):
    service, uploader = _service(_Uploader(fail=True))
    monkeypatch.setattr(image_assets, "MAX_TOTAL_IMAGE_BYTES", 5)

    assert service.upload_embedded(b"1234", extension="png") is None
    assert service.upload_embedded(b"56", extension="png") is None
    assert len(uploader.calls) == 1


@pytest.mark.parametrize(
    "uploader",
    [_Uploader(fail=True), _Uploader(preview_url=None)],
)
def test_upload_failure_or_missing_preview_is_non_fatal(uploader):
    service, _ = _service(uploader)

    assert service.upload_embedded(b"image", extension="png") is None

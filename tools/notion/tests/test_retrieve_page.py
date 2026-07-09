import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.retrieve_page import RetrievePageTool, _guess_image_filename, _guess_image_mime_type


class _Response:
    def __init__(self, content=b"binarydata", headers=None, status_code=200):
        self.content = content
        self.headers = headers or {}
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size=8192):
        for i in range(0, len(self.content), chunk_size):
            yield self.content[i : i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _MessageToolMixin:
    def create_text_message(self, value):
        return {"type": "text", "value": value}

    def create_json_message(self, value):
        return {"type": "json", "value": value}

    def create_blob_message(self, blob, meta=None):
        return {"type": "blob", "blob": blob, "meta": meta}


def _tool():
    tool = object.__new__(RetrievePageTool)
    tool.runtime = SimpleNamespace(credentials={"integration_token": "secret-token"})
    for name in ("create_text_message", "create_json_message", "create_blob_message"):
        setattr(tool, name, getattr(_MessageToolMixin, name).__get__(tool, RetrievePageTool))
    return tool


def _page_data():
    return {
        "id": "page-123",
        "created_time": "2024-01-01T00:00:00.000Z",
        "last_edited_time": "2024-01-02T00:00:00.000Z",
        "archived": False,
        "properties": {
            "Name": {"type": "title", "title": [{"plain_text": "My Page"}]},
        },
    }


def _image_block(block_id, url, caption=""):
    return {
        "id": block_id,
        "type": "image",
        "has_children": False,
        "image": {
            "type": "file",
            "file": {"url": url},
            "caption": [{"plain_text": caption}] if caption else [],
        },
    }


def _paragraph_block(block_id, text):
    return {
        "id": block_id,
        "type": "paragraph",
        "has_children": False,
        "paragraph": {"rich_text": [{"plain_text": text}]},
    }


def _patch_notion(monkeypatch, blocks):
    from tools import retrieve_page
    from tools.notion_client import NotionClient

    monkeypatch.setattr(NotionClient, "retrieve_page", lambda self, page_id: _page_data())
    monkeypatch.setattr(
        NotionClient,
        "retrieve_block_children",
        lambda self, block_id, page_size=100, start_cursor=None: {
            "results": blocks,
            "has_more": False,
            "next_cursor": None,
        },
    )
    monkeypatch.setattr(NotionClient, "format_page_url", lambda self, page_id: f"https://notion.so/{page_id}")
    return retrieve_page


def test_guess_image_mime_type_prefers_content_type_header():
    response = _Response(headers={"Content-Type": "image/jpeg; charset=binary"})
    assert _guess_image_mime_type(response, "https://example.com/photo.jpg") == "image/jpeg"


def test_guess_image_mime_type_falls_back_to_url_extension():
    response = _Response(headers={})
    assert _guess_image_mime_type(response, "https://example.com/photo.gif?X-Amz=abc") == "image/gif"


def test_guess_image_mime_type_falls_back_when_content_type_is_generic():
    response = _Response(headers={"Content-Type": "application/octet-stream"})
    assert _guess_image_mime_type(response, "https://example.com/photo.jpg") == "image/jpeg"


def test_guess_image_mime_type_falls_back_when_content_type_is_not_an_image():
    response = _Response(headers={"Content-Type": "text/html"})
    assert _guess_image_mime_type(response, "https://example.com/photo.jpg") == "image/jpeg"


def test_guess_image_mime_type_falls_back_to_default():
    response = _Response(headers={})
    assert _guess_image_mime_type(response, "https://example.com/no-extension") == "image/png"


def test_guess_image_filename_uses_url_path_segment():
    assert _guess_image_filename("https://example.com/a/b/photo.png?X-Amz=abc", "block-1", "image/png") == "photo.png"


def test_guess_image_filename_falls_back_to_block_id():
    assert _guess_image_filename("https://example.com/", "block-1", "image/jpeg") == "block-1.jpg"


def test_image_block_is_downloaded_and_returned_as_blob_message(monkeypatch):
    blocks = [_image_block("block-1", "https://s3.example.com/path/photo.png?X-Amz=abc", caption="A photo")]
    retrieve_page = _patch_notion(monkeypatch, blocks)

    def fake_get(url, timeout=None, stream=None):
        assert url == "https://s3.example.com/path/photo.png?X-Amz=abc"
        assert stream is True
        return _Response(content=b"pngbytes", headers={"Content-Type": "image/png"})

    monkeypatch.setattr(retrieve_page.requests, "get", fake_get)

    messages = list(_tool()._invoke({"page_id": "page-123"}))

    blob_messages = [m for m in messages if m["type"] == "blob"]
    assert len(blob_messages) == 1
    assert blob_messages[0]["blob"] == b"pngbytes"
    assert blob_messages[0]["meta"] == {"mime_type": "image/png", "filename": "photo.png"}

    json_message = next(m for m in messages if m["type"] == "json")
    image_block = json_message["value"]["content"][0]
    assert image_block["url"] == "https://s3.example.com/path/photo.png?X-Amz=abc"
    assert image_block["caption"] == "A photo"


def test_include_content_false_skips_image_download(monkeypatch):
    blocks = [_image_block("block-1", "https://s3.example.com/path/photo.png")]
    retrieve_page = _patch_notion(monkeypatch, blocks)

    def fake_get(*args, **kwargs):
        raise AssertionError("Should not download images when include_content is False")

    monkeypatch.setattr(retrieve_page.requests, "get", fake_get)

    messages = list(_tool()._invoke({"page_id": "page-123", "include_content": False}))

    assert not [m for m in messages if m["type"] == "blob"]
    json_message = next(m for m in messages if m["type"] == "json")
    assert "content" not in json_message["value"]


def test_max_images_limits_downloads_and_reports_skipped(monkeypatch):
    blocks = [
        _image_block("block-1", "https://s3.example.com/a.png"),
        _image_block("block-2", "https://s3.example.com/b.png"),
        _image_block("block-3", "https://s3.example.com/c.png"),
    ]
    retrieve_page = _patch_notion(monkeypatch, blocks)

    monkeypatch.setattr(
        retrieve_page.requests,
        "get",
        lambda url, timeout=None, stream=None: _Response(content=b"x", headers={"Content-Type": "image/png"}),
    )

    messages = list(_tool()._invoke({"page_id": "page-123", "max_images": 1}))

    assert len([m for m in messages if m["type"] == "blob"]) == 1
    json_message = next(m for m in messages if m["type"] == "json")
    assert json_message["value"]["images_skipped"] == 2


def test_failed_image_download_does_not_crash_others(monkeypatch):
    blocks = [
        _image_block("block-1", "https://s3.example.com/broken.png"),
        _image_block("block-2", "https://s3.example.com/ok.png"),
    ]
    retrieve_page = _patch_notion(monkeypatch, blocks)

    def fake_get(url, timeout=None, stream=None):
        if "broken" in url:
            raise Exception("connection reset")
        return _Response(content=b"okbytes", headers={"Content-Type": "image/png"})

    monkeypatch.setattr(retrieve_page.requests, "get", fake_get)

    messages = list(_tool()._invoke({"page_id": "page-123"}))

    blob_messages = [m for m in messages if m["type"] == "blob"]
    assert len(blob_messages) == 1
    assert blob_messages[0]["blob"] == b"okbytes"

    summary = next(m for m in messages if m["type"] == "text" and m["value"].startswith("Downloaded"))
    assert summary["value"] == "Downloaded 1 image(s), 1 failed"


def test_page_without_images_yields_no_blob_messages(monkeypatch):
    blocks = [_paragraph_block("block-1", "Just text, no images here")]
    retrieve_page = _patch_notion(monkeypatch, blocks)

    def fake_get(*args, **kwargs):
        raise AssertionError("Should not attempt any download when there are no images")

    monkeypatch.setattr(retrieve_page.requests, "get", fake_get)

    messages = list(_tool()._invoke({"page_id": "page-123"}))

    assert not [m for m in messages if m["type"] == "blob"]


def test_image_over_max_size_via_content_length_header_is_skipped(monkeypatch):
    blocks = [_image_block("block-1", "https://s3.example.com/huge.png")]
    retrieve_page = _patch_notion(monkeypatch, blocks)
    monkeypatch.setattr(retrieve_page, "DEFAULT_MAX_IMAGE_SIZE", 10)

    def fake_get(url, timeout=None, stream=None):
        return _Response(
            content=b"x" * 20,
            headers={"Content-Type": "image/png", "Content-Length": "20"},
        )

    monkeypatch.setattr(retrieve_page.requests, "get", fake_get)

    messages = list(_tool()._invoke({"page_id": "page-123"}))

    assert not [m for m in messages if m["type"] == "blob"]
    summary = next(m for m in messages if m["type"] == "text" and m["value"].startswith("Downloaded"))
    assert summary["value"] == "Downloaded 0 image(s), 1 failed"


def test_image_over_max_size_without_content_length_is_aborted_mid_stream(monkeypatch):
    blocks = [_image_block("block-1", "https://s3.example.com/huge.png")]
    retrieve_page = _patch_notion(monkeypatch, blocks)
    monkeypatch.setattr(retrieve_page, "DEFAULT_MAX_IMAGE_SIZE", 10)

    def fake_get(url, timeout=None, stream=None):
        return _Response(content=b"x" * 20, headers={"Content-Type": "image/png"})

    monkeypatch.setattr(retrieve_page.requests, "get", fake_get)

    messages = list(_tool()._invoke({"page_id": "page-123"}))

    assert not [m for m in messages if m["type"] == "blob"]


def test_cumulative_size_limit_stops_further_downloads(monkeypatch):
    blocks = [
        _image_block("block-1", "https://s3.example.com/a.png"),
        _image_block("block-2", "https://s3.example.com/b.png"),
        _image_block("block-3", "https://s3.example.com/c.png"),
    ]
    retrieve_page = _patch_notion(monkeypatch, blocks)
    monkeypatch.setattr(retrieve_page, "DEFAULT_MAX_IMAGE_SIZE", 10)
    monkeypatch.setattr(retrieve_page, "DEFAULT_MAX_CUMULATIVE_IMAGE_SIZE", 15)

    monkeypatch.setattr(
        retrieve_page.requests,
        "get",
        lambda url, timeout=None, stream=None: _Response(content=b"x" * 10, headers={"Content-Type": "image/png"}),
    )

    messages = list(_tool()._invoke({"page_id": "page-123"}))

    blob_messages = [m for m in messages if m["type"] == "blob"]
    assert len(blob_messages) == 1
    summary = next(m for m in messages if m["type"] == "text" and m["value"].startswith("Downloaded"))
    assert summary["value"] == "Downloaded 1 image(s), 2 failed"

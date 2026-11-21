import pytest

from tests.fakes import make_tool
from tools.download_attachment import DownloadAttachmentTool


def test_decode_base64url_reports_decode_failure():
    tool = make_tool(DownloadAttachmentTool, {})

    with pytest.raises(ValueError, match="Failed to decode base64url data"):
        tool._decode_base64url("!!!not-base64!!!")


def test_decode_base64url_returns_bytes_for_valid_input():
    tool = make_tool(DownloadAttachmentTool, {})

    assert tool._decode_base64url("aGVsbG8") == b"hello"

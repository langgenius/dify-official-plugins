import io
import runpy
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolRuntime
from dify_plugin.file.entities import FileType
from dify_plugin.file.file import File
from PIL import Image


@pytest.fixture
def image_url() -> Iterator[str]:
    png = io.BytesIO()
    Image.new("RGB", (20, 20), "red").save(png, format="PNG")

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(png.getvalue() if self.path == "/logo.png" else b"not an image")

        def log_message(self, *args: object) -> None:
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.fixture
def tool() -> Tool:
    source = Path(__file__).resolve().parents[1] / "tools" / "qrcode_generator.py"
    tool_class = runpy.run_path(str(source))["QRCodeGeneratorTool"]
    return tool_class(
        runtime=ToolRuntime(credentials={}, user_id="test", session_id="test"),
        session=None,
    )


def test_embedded_image_completes(tool: Tool, image_url: str) -> None:
    image = File(url=f"{image_url}/logo.png", type=FileType.IMAGE, mime_type="image/png")
    messages = list(
        tool.invoke(
            {
                "content": "hello",
                "border": 2,
                "error_correction": "M",
                "embedded_image": image,
            }
        )
    )
    assert len(messages) == 1 and messages[0].type.value == "blob"
    with Image.open(io.BytesIO(messages[0].message.blob)) as qr:
        assert qr.format == "PNG"
        assert qr.convert("RGB").getpixel((qr.width // 2, qr.height // 2)) == (255, 0, 0)


def test_invalid_image_preserves_error_message(tool: Tool, image_url: str) -> None:
    image = File(url=f"{image_url}/invalid.png", type=FileType.IMAGE, mime_type="image/png")
    messages = list(
        tool.invoke(
            {
                "content": "hello",
                "border": 2,
                "error_correction": "M",
                "embedded_image": image,
            }
        )
    )
    assert len(messages) == 1
    assert messages[0].message.text == "Failed to generate QR code"


@pytest.mark.parametrize("error_correction", ["L", "M", "Q", "H"])
def test_plain_qrcode(tool: Tool, error_correction: str) -> None:
    messages = list(
        tool.invoke(
            {
                "content": "hello",
                "border": 2,
                "error_correction": error_correction,
                "output_filename": "ticket.png",
            }
        )
    )
    assert len(messages) == 1 and messages[0].type.value == "blob"
    assert messages[0].meta == {"mime_type": "image/png", "filename": "ticket.png"}
    with Image.open(io.BytesIO(messages[0].message.blob)) as qr:
        assert qr.format == "PNG"
        qr.load()

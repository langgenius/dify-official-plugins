import io
import logging
import os
import tempfile
from typing import Any, Generator, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q
from qrcode.image.base import BaseImage
from qrcode.image.pure import PyPNGImage
from qrcode.image.styledpil import StyledPilImage
from qrcode.main import QRCode


class QRCodeGeneratorTool(Tool):
    error_correction_levels: dict[str, int] = {
        "L": ERROR_CORRECT_L,
        "M": ERROR_CORRECT_M,
        "Q": ERROR_CORRECT_Q,
        "H": ERROR_CORRECT_H,
    }

    def _invoke(
            self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        content = tool_parameters.get("content", "")
        if not content:
            yield self.create_text_message("Invalid parameter content")
        border = tool_parameters.get("border", 0)
        if border < 0 or border > 100:
            yield self.create_text_message("Invalid parameter border")
        error_correction = tool_parameters.get("error_correction", "")
        if error_correction not in self.error_correction_levels:
            yield self.create_text_message("Invalid parameter error_correction")

        embedded_image: Optional[File] = tool_parameters.get("embedded_image")
        embedded_image_path: Optional[str] = None
        if embedded_image:
            tmp_embedded_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp_embedded_file.write(embedded_image.blob)
            tmp_embedded_file.flush()
            embedded_image_path = tmp_embedded_file.name

        output_filename: Optional[str] = tool_parameters.get("output_filename")
        if output_filename and not output_filename.lower().endswith(".png"):
            final_output_filename = f"output_filename.png"
        else:
            final_output_filename = output_filename

        try:
            image = self._generate_qrcode(content, border, error_correction, embedded_image_path=embedded_image_path)
            image_bytes = self._image_to_byte_array(image)
            yield self.create_blob_message(
                blob=image_bytes,
                meta={
                    "mime_type": "image/png",
                    "filename": final_output_filename,
                },
            )
        except Exception:
            logging.exception(f"Failed to generate QR code for content: {content}")
            yield self.create_text_message("Failed to generate QR code")
        finally:
            if embedded_image_path:
                os.unlink(embedded_image_path)
            pass

    def _generate_qrcode(self, content: str, border: int, error_correction: str,
                         embedded_image_path: Optional[str]) -> BaseImage:
        if embedded_image_path:
            image_factory = StyledPilImage
            error_correction = "H"
            embedded_image_ratio = 0.3
        else:
            image_factory = PyPNGImage
            embedded_image_ratio = None

        qr = QRCode(
            image_factory=image_factory,
            error_correction=self.error_correction_levels.get(error_correction),
            border=border
        )
        qr.add_data(data=content)
        qr.make(fit=True)
        img = qr.make_image(
            embedded_image_path=embedded_image_path,
            embedded_image_ratio=embedded_image_ratio,
        )
        return img

    @staticmethod
    def _image_to_byte_array(image: BaseImage) -> bytes:
        byte_stream = io.BytesIO()
        image.save(byte_stream)
        return byte_stream.getvalue()

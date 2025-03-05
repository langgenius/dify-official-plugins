import base64
import io
from collections.abc import Generator
from typing import Any, Optional

import PyPDF2
from dify_plugin.entities import I18nObject
from dify_plugin.entities.tool import ToolInvokeMessage, ToolParameter
from dify_plugin import Tool
from dify_plugin.file.file import File

class PDFPageCounterTool(Tool):
    """
    A tool for counting the total number of pages in a PDF file.
    This tool takes a PDF file (base64 encoded or Dify file object) as input,
    and returns the total number of pages in the PDF directly.
    """

    def _invoke(
        self,
        tool_parameters: dict[str, Any],
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        app_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Count the total number of pages in a PDF file and return just the number.

        Args:
            tool_parameters (dict[str, Any]): Parameters for the tool
                - pdf_content (str or File): Base64 encoded PDF file content or Dify File object
            user_id (Optional[str], optional): The ID of the user invoking the tool. Defaults to None.
            conversation_id (Optional[str], optional): The conversation ID. Defaults to None.
            app_id (Optional[str], optional): The app ID. Defaults to None.
            message_id (Optional[str], optional): The message ID. Defaults to None.

        Returns:
            Generator[ToolInvokeMessage, None, None]: Generator yielding just the page count number
            
        Raises:
            ValueError: If the PDF content format is invalid or required parameters are missing
            Exception: For any other errors during PDF processing
        """
        try:
            pdf_content = tool_parameters.get("pdf_content")
            if pdf_content is None:
                raise ValueError("Missing required parameter: pdf_content")
            
            if isinstance(pdf_content, File):
                pdf_bytes = pdf_content.blob
            elif isinstance(pdf_content, str):
                try:
                    pdf_bytes = base64.b64decode(pdf_content)
                except Exception:
                    raise ValueError("Invalid base64 encoding for PDF content")
            else:
                raise ValueError("Invalid PDF content format. Expected base64 encoded string or File object.")
                
            pdf_file = io.BytesIO(pdf_bytes)
            
            try:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
            except Exception as e:
                raise ValueError(f"Invalid PDF file: {str(e)}")
            
            total_pages = len(pdf_reader.pages)
            
            yield self.create_text_message(str(total_pages))
            
        except ValueError as e:
            raise
        except Exception as e:
            raise Exception(f"Error counting pages in PDF: {str(e)}")
            
    def get_runtime_parameters(
        self,
        conversation_id: Optional[str] = None,
        app_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> list[ToolParameter]:
        """
        Get the runtime parameters for the PDF page counter tool.
        
        Returns:
            list[ToolParameter]: List of tool parameters
        """
        parameters = [
            ToolParameter(
                name="pdf_content",
                label=I18nObject(en_US="PDF Content", zh_Hans="PDF 内容"),
                human_description=I18nObject(
                    en_US="PDF file content (base64 encoded)",
                    zh_Hans="PDF 文件内容（base64 编码）",
                ),
                type=ToolParameter.ToolParameterType.FILE,
                form=ToolParameter.ToolParameterForm.FORM,
                required=True,
                file_accepts=["application/pdf"],
            ),
        ]
        return parameters 
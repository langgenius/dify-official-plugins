import base64
import io
from collections.abc import Generator
from typing import Any, Optional

import PyPDF2
from dify_plugin.entities import I18nObject
from dify_plugin.entities.tool import ToolInvokeMessage, ToolParameter
from dify_plugin import Tool
from dify_plugin.file.file import File

class PDFExtractorTool(Tool):
    """
    A tool for extracting pages from PDF files.
    This tool takes a PDF file (base64 encoded or Dify file object) and a page number as input,
    and returns the specified page as a PDF blob.
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
        Extract a specific page from a PDF file.

        Args:
            tool_parameters (dict[str, Any]): Parameters for the tool
                - pdf_content (str or File): Base64 encoded PDF file content or Dify File object
                - page_number (int): Page number to extract (1-indexed as users expect)
            user_id (Optional[str], optional): The ID of the user invoking the tool. Defaults to None.
            conversation_id (Optional[str], optional): The conversation ID. Defaults to None.
            app_id (Optional[str], optional): The app ID. Defaults to None.
            message_id (Optional[str], optional): The message ID. Defaults to None.

        Returns:
            Generator[ToolInvokeMessage, None, None]: Generator yielding the PDF page blob
            
        Raises:
            ValueError: If the PDF content format is invalid, required parameters are missing, or the page number is out of range
            Exception: For any other errors during PDF processing
        """
        try:
            pdf_content = tool_parameters.get("pdf_content")
            if pdf_content is None:
                raise ValueError("Missing required parameter: pdf_content")
                
            page_number_param = tool_parameters.get("page_number")
            if page_number_param is None:
                raise ValueError("Missing required parameter: page_number")
                
            try:
                user_page_number = int(page_number_param)
                if user_page_number < 1:
                    raise ValueError(f"Page number must be at least 1. You entered: {user_page_number}")
                page_number = user_page_number - 1
            except (ValueError, TypeError):
                raise ValueError(f"Invalid page number format: {page_number_param}. Must be an integer.")
            
            if isinstance(pdf_content, File):
                pdf_bytes = pdf_content.blob
                original_filename = pdf_content.filename or "document"
            elif isinstance(pdf_content, str):
                try:
                    pdf_bytes = base64.b64decode(pdf_content)
                except Exception:
                    raise ValueError("Invalid base64 encoding for PDF content")
                original_filename = "document"
            else:
                raise ValueError("Invalid PDF content format. Expected base64 encoded string or File object.")
                
            pdf_file = io.BytesIO(pdf_bytes)
            
            try:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
            except Exception as e:
                raise ValueError(f"Invalid PDF file: {str(e)}")
            
            total_pages = len(pdf_reader.pages)
            if page_number < 0 or page_number >= total_pages:
                raise ValueError(f"Invalid page number. The PDF has {total_pages} pages (1-{total_pages}). You entered: {user_page_number}.")
            
            output = PyPDF2.PdfWriter()
            output.add_page(pdf_reader.pages[page_number])
            
            page_buffer = io.BytesIO()
            output.write(page_buffer)
            page_buffer.seek(0)
            
            if original_filename.lower().endswith('.pdf'):
                base_filename = original_filename[:-4]
            else:
                base_filename = original_filename
                
            output_filename = f"{base_filename}_page{user_page_number}.pdf"
            
            yield self.create_text_message(f"Successfully extracted page {user_page_number} from PDF")
            
            yield self.create_blob_message(
                blob=page_buffer.getvalue(),
                meta={
                    "mime_type": "application/pdf",
                    "filename": output_filename
                },
            )
            
        except ValueError as e:
            raise
        except Exception as e:
            raise Exception(f"Error extracting page from PDF: {str(e)}")
            
    def get_runtime_parameters(
        self,
        conversation_id: Optional[str] = None,
        app_id: Optional[str] = None,
        message_id: Optional[str] = None,
    ) -> list[ToolParameter]:
        """
        Get the runtime parameters for the PDF extractor tool.
        
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
            ToolParameter(
                name="page_number",
                label=I18nObject(en_US="Page Number", zh_Hans="页码"),
                human_description=I18nObject(
                    en_US="Page number to extract (starting from 1)",
                    zh_Hans="要提取的页码（从1开始）",
                ),
                type=ToolParameter.ToolParameterType.NUMBER,
                form=ToolParameter.ToolParameterForm.FORM,
                required=True,
                default=1,
            ),
        ]
        return parameters

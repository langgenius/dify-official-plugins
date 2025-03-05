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
        """
        try:
            # Get parameters
            pdf_content = tool_parameters.get("pdf_content")
            # Convert from 1-indexed (user-friendly) to 0-indexed (code-friendly)
            user_page_number = int(tool_parameters.get("page_number", 1))
            page_number = user_page_number - 1  # Convert to 0-indexed
            
            # Handle different types of pdf_content
            if isinstance(pdf_content, File):
                # If it's a Dify File object, get the blob directly
                pdf_bytes = pdf_content.blob
                original_filename = pdf_content.filename or "document"
            elif isinstance(pdf_content, str):
                # If it's a base64 encoded string, decode it
                pdf_bytes = base64.b64decode(pdf_content)
                original_filename = "document"
            else:
                error_message = "Invalid PDF content format. Expected base64 encoded string or File object."
                yield self.create_text_message(error_message)
                return
                
            pdf_file = io.BytesIO(pdf_bytes)
            
            # Open the PDF file
            pdf_reader = PyPDF2.PdfReader(pdf_file)
            
            # Check if the page number is valid
            total_pages = len(pdf_reader.pages)
            if page_number < 0 or page_number >= total_pages:
                error_message = f"Invalid page number. The PDF has {total_pages} pages (1-{total_pages}). You entered: {user_page_number}."
                yield self.create_text_message(error_message)
                return
            
            # Create a new PDF with just the extracted page
            output = PyPDF2.PdfWriter()
            output.add_page(pdf_reader.pages[page_number])
            
            # Save the page to a bytes buffer
            page_buffer = io.BytesIO()
            output.write(page_buffer)
            page_buffer.seek(0)
            
            # Create output filename - use the user-friendly page number in the filename
            # Remove .pdf extension if present
            if original_filename.lower().endswith('.pdf'):
                base_filename = original_filename[:-4]
            else:
                base_filename = original_filename
                
            output_filename = f"{base_filename}_page{user_page_number}.pdf"
            
            # Return success message
            yield self.create_text_message(f"Successfully extracted page {user_page_number} from PDF")
            
            # Return the PDF page as a blob
            yield self.create_blob_message(
                blob=page_buffer.getvalue(),
                meta={
                    "mime_type": "application/pdf",
                    "filename": output_filename
                },
            )
            
        except Exception as e:
            error_message = f"Error extracting page from PDF: {str(e)}"
            yield self.create_text_message(error_message)
            
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

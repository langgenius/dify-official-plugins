"""
Comprehensive test suite for Gemini API document filtering functionality.

This module tests the file filtering logic for documents specifically,
with extensible architecture for future multimodal testing.

Structure:
1. Unit tests (no API key required)
2. Integration tests (API key required, real Gemini API calls)
"""

import base64
import os
from contextlib import suppress
from typing import Dict, Optional
from unittest.mock import Mock, patch

import pytest
from dify_plugin.entities.model.message import (
    UserPromptMessage,
    DocumentPromptMessageContent,
    TextPromptMessageContent,
)
from dotenv import load_dotenv
from google import genai
from google.genai import types

try:
    from models.llm.llm import GoogleLargeLanguageModel
except ImportError:
    import sys
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from models.llm.llm import GoogleLargeLanguageModel

# Load environment variables
load_dotenv()

# Shared test configuration for minimal cost
GEMINI_TEST_CONFIG = {"model": "gemini-2.5-flash-lite", "max_output_tokens": 5, "temperature": 0.1}


class MemoryFileCache:
    """In-memory file cache for testing (no persistence)."""

    def __init__(self, namespace: str = "default"):
        self._cache: Dict[str, Dict] = {}
        self.namespace = namespace

    def _namespaced_key(self, key: str) -> str:
        """Add namespace to cache key to prevent conflicts between test classes."""
        return f"{self.namespace}:{key}"

    def exists(self, key: str) -> bool:
        return self._namespaced_key(key) in self._cache

    def get(self, key: str) -> Optional[str]:
        return self._cache.get(self._namespaced_key(key), {}).get("value")

    def setex(self, key: str, expires_in_seconds: int, value: str) -> None:
        self._cache[self._namespaced_key(key)] = {"value": value}

    def clear(self):
        """Clear cache for test cleanup."""
        self._cache.clear()


class DocumentGenerator:
    """Generate test documents in memory."""

    @staticmethod
    def create_pdf_bytes() -> bytes:
        """Create minimal valid PDF."""
        return b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]/Contents 4 0 R>>endobj
4 0 obj<</Length 44>>stream
BT/F1 12 Tf 100 700 Td(Test)Tj ET
endstream endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000115 00000 n 
0000000274 00000 n 
trailer<</Size 5/Root 1 0 R>>
startxref
362
%%EOF"""

    @staticmethod
    def create_text_bytes(content: str = "Test document content") -> bytes:
        """Create text document."""
        return content.encode("utf-8")

    @staticmethod
    def create_docx_bytes() -> bytes:
        """Create minimal DOCX-like bytes (ZIP structure)."""
        # DOCX is a ZIP file, minimal ZIP structure
        return b"PK\x03\x04" + b"\x00" * 20

    @staticmethod
    def create_html_bytes(content: str = "<html><body>Test</body></html>") -> bytes:
        """Create HTML document."""
        return content.encode("utf-8")

    @staticmethod
    def create_markdown_bytes(content: str = "# Test Markdown\n\nContent") -> bytes:
        """Create Markdown document."""
        return content.encode("utf-8")


class TestDocumentFilteringUnit:
    """Unit tests for document filtering (no API key required)."""

    def setup_method(self):
        """Setup test fixtures."""
        self.llm = GoogleLargeLanguageModel([])
        self.mock_client = Mock(spec=genai.Client)
        self.config = types.GenerateContentConfig()

        # Create memory cache for testing with unit test namespace
        self.memory_cache = MemoryFileCache(namespace="unit_test")

        # Mock file upload response
        self.mock_file = Mock()
        self.mock_file.uri = "gs://test-bucket/test-file"
        self.mock_file.mime_type = "application/pdf"
        self.mock_file.state.name = "ACTIVE"
        self.mock_client.files.upload.return_value = self.mock_file
        self.mock_client.files.get.return_value = self.mock_file

        # Patch the file cache module-wide for this test class
        # Try different patch paths to handle different execution contexts
        self.cache_patcher = None
        for patch_path in ["models.llm.llm.file_cache", "llm.file_cache"]:
            try:
                self.cache_patcher = patch(patch_path, self.memory_cache)
                self.cache_patcher.start()
                break
            except (ImportError, AttributeError):
                if self.cache_patcher:
                    with suppress(Exception):
                        self.cache_patcher.stop()
                continue
        if not self.cache_patcher:
            # Fallback: patch the module directly
            import llm

            self.original_file_cache = llm.file_cache
            llm.file_cache = self.memory_cache

    def teardown_method(self):
        """Cleanup after each test."""
        if self.cache_patcher:
            with suppress(Exception):
                self.cache_patcher.stop()
        elif hasattr(self, "original_file_cache"):
            # Restore original file_cache if we patched it directly
            import llm

            llm.file_cache = self.original_file_cache

        # Clear cache before resetting mocks to prevent cache pollution
        self.memory_cache.clear()

        # Reset mock states to prevent pollution between tests
        self.mock_client.reset_mock()
        self.mock_file.reset_mock()

        # Reset file mock attributes to original values
        self.mock_file.uri = "gs://test-bucket/test-file"
        self.mock_file.mime_type = "application/pdf"
        self.mock_file.state.name = "ACTIVE"
        self.mock_client.files.upload.return_value = self.mock_file
        self.mock_client.files.get.return_value = self.mock_file

        # Clear any side effects from previous tests
        self.mock_client.files.upload.side_effect = None

    def test_supported_pdf_document(self):
        """Test that PDF documents are uploaded successfully."""
        pdf_bytes = DocumentGenerator.create_pdf_bytes()
        base64_data = base64.b64encode(pdf_bytes).decode()

        message = UserPromptMessage(
            content=[
                TextPromptMessageContent(data="Analyze this PDF:"),
                DocumentPromptMessageContent(
                    format="pdf", base64_data=base64_data, mime_type="application/pdf"
                ),
            ]
        )

        self.mock_file.mime_type = "application/pdf"

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):

            contents = self.llm._build_gemini_contents(
                prompt_messages=[message], genai_client=self.mock_client, config=self.config
            )

        # Should have text + PDF
        assert len(contents) == 1
        assert len(contents[0].parts) == 2
        assert contents[0].parts[0].text == "Analyze this PDF:"
        assert contents[0].parts[1].file_data.file_uri == "gs://test-bucket/test-file"
        assert contents[0].parts[1].file_data.mime_type == "application/pdf"

    def test_supported_text_document(self):
        """Test that plain text documents are uploaded successfully."""
        text_bytes = DocumentGenerator.create_text_bytes("Sample text content")
        base64_data = base64.b64encode(text_bytes).decode()

        message = UserPromptMessage(
            content=[
                DocumentPromptMessageContent(
                    format="txt", base64_data=base64_data, mime_type="text/plain"
                )
            ]
        )

        self.mock_file.mime_type = "text/plain"

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):

            contents = self.llm._build_gemini_contents(
                prompt_messages=[message], genai_client=self.mock_client, config=self.config
            )

        assert len(contents) == 1
        assert len(contents[0].parts) == 1
        assert contents[0].parts[0].file_data.mime_type == "text/plain"

    def test_supported_html_document(self):
        """Test that HTML documents are uploaded successfully."""
        html_bytes = DocumentGenerator.create_html_bytes()
        base64_data = base64.b64encode(html_bytes).decode()

        message = UserPromptMessage(
            content=[
                DocumentPromptMessageContent(
                    format="html", base64_data=base64_data, mime_type="text/html"
                )
            ]
        )

        self.mock_file.mime_type = "text/html"

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):

            contents = self.llm._build_gemini_contents(
                prompt_messages=[message], genai_client=self.mock_client, config=self.config
            )

        assert len(contents) == 1
        assert len(contents[0].parts) == 1
        assert contents[0].parts[0].file_data.mime_type == "text/html"

    def test_supported_markdown_document(self):
        """Test that Markdown documents are uploaded successfully."""
        md_bytes = DocumentGenerator.create_markdown_bytes()
        base64_data = base64.b64encode(md_bytes).decode()

        message = UserPromptMessage(
            content=[
                DocumentPromptMessageContent(
                    format="md", base64_data=base64_data, mime_type="text/markdown"
                )
            ]
        )

        self.mock_file.mime_type = "text/markdown"

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):

            contents = self.llm._build_gemini_contents(
                prompt_messages=[message], genai_client=self.mock_client, config=self.config
            )

        assert len(contents) == 1
        assert len(contents[0].parts) == 1
        assert contents[0].parts[0].file_data.mime_type == "text/markdown"

    def test_unsupported_docx_document_filtered_by_mime_type(self):
        """Test that DOCX documents are filtered out by MIME type."""
        docx_bytes = DocumentGenerator.create_docx_bytes()
        base64_data = base64.b64encode(docx_bytes).decode()

        message = UserPromptMessage(
            content=[
                TextPromptMessageContent(data="Check this document:"),
                DocumentPromptMessageContent(
                    format="docx",
                    base64_data=base64_data,
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            ]
        )

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"), patch(
            "logging.debug"
        ) as mock_log:

            contents = self.llm._build_gemini_contents(
                prompt_messages=[message], genai_client=self.mock_client, config=self.config
            )

        # Should only have text, DOCX filtered out
        assert len(contents) == 1
        assert len(contents[0].parts) == 1
        assert contents[0].parts[0].text == "Check this document:"

        # Verify filtering was logged
        mock_log.assert_called()
        log_message = mock_log.call_args[0][0]
        assert "Skipping unsupported file" in log_message

    def test_unsupported_office_documents_filtered(self):
        """Test that all Microsoft Office documents are filtered out."""
        office_docs = [
            ("doc", "application/msword"),
            ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            ("xls", "application/vnd.ms-excel"),
            ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            ("ppt", "application/vnd.ms-powerpoint"),
            ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ]

        for format_ext, mime_type in office_docs:
            message = UserPromptMessage(
                content=[
                    DocumentPromptMessageContent(
                        format=format_ext,
                        base64_data=base64.b64encode(b"test").decode(),
                        mime_type=mime_type,
                    )
                ]
            )

            with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):

                contents = self.llm._build_gemini_contents(
                    prompt_messages=[message], genai_client=self.mock_client, config=self.config
                )

            # Should be filtered out
            assert len(contents) == 1
            assert len(contents[0].parts) == 0, f"Failed for {format_ext}"

    def test_unsupported_extensions_filtered(self):
        """Test that documents with unsupported extensions are filtered out."""
        unsupported_extensions = ["docx", "xlsx", "pptx", "rtf", "wps", "odt"]

        for ext in unsupported_extensions:
            message = UserPromptMessage(
                content=[
                    DocumentPromptMessageContent(
                        format=ext,
                        base64_data=base64.b64encode(b"test").decode(),
                        mime_type="application/octet-stream",  # Generic MIME type
                    )
                ]
            )

            with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):

                contents = self.llm._build_gemini_contents(
                    prompt_messages=[message], genai_client=self.mock_client, config=self.config
                )

            # Should be filtered out
            assert len(contents) == 1
            assert len(contents[0].parts) == 0, f"Failed for extension {ext}"

    def test_case_insensitive_extension_filtering(self):
        """Test that extension filtering is case-insensitive."""
        case_variants = ["DOCX", "Docx", "dOcX", "DOC", "XLSX"]

        for ext in case_variants:
            message = UserPromptMessage(
                content=[
                    DocumentPromptMessageContent(
                        format=ext,
                        base64_data=base64.b64encode(b"test").decode(),
                        mime_type="application/octet-stream",
                    )
                ]
            )

            with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):

                contents = self.llm._build_gemini_contents(
                    prompt_messages=[message], genai_client=self.mock_client, config=self.config
                )

            # Should be filtered regardless of case
            assert len(contents) == 1
            assert len(contents[0].parts) == 0, f"Failed for case variant {ext}"

    def test_mixed_supported_unsupported_documents(self):
        """Test filtering with mixed supported and unsupported documents."""
        message = UserPromptMessage(
            content=[
                TextPromptMessageContent(data="Analyze these documents:"),
                # Supported PDF
                DocumentPromptMessageContent(
                    format="pdf",
                    base64_data=base64.b64encode(DocumentGenerator.create_pdf_bytes()).decode(),
                    mime_type="application/pdf",
                ),
                # Unsupported DOCX
                DocumentPromptMessageContent(
                    format="docx",
                    base64_data=base64.b64encode(DocumentGenerator.create_docx_bytes()).decode(),
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
                # Supported plain text
                DocumentPromptMessageContent(
                    format="txt",
                    base64_data=base64.b64encode(DocumentGenerator.create_text_bytes()).decode(),
                    mime_type="text/plain",
                ),
                TextPromptMessageContent(data="What do you see?"),
            ]
        )

        # Mock different responses for each upload using separate mock objects
        upload_count = 0

        def upload_side_effect(*args, **kwargs):
            nonlocal upload_count
            upload_count += 1

            # Create separate mock file objects to avoid shared state
            mock_file = Mock()
            mock_file.uri = "gs://test-bucket/test-file"
            mock_file.state.name = "ACTIVE"

            if upload_count == 1:
                mock_file.mime_type = "application/pdf"
            elif upload_count == 2:
                mock_file.mime_type = "text/plain"
            else:
                mock_file.mime_type = "application/octet-stream"

            return mock_file

        self.mock_client.files.upload.side_effect = upload_side_effect

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):

            contents = self.llm._build_gemini_contents(
                prompt_messages=[message], genai_client=self.mock_client, config=self.config
            )

        # Should have: text + PDF + text file + final text (DOCX filtered out)
        assert len(contents) == 1
        assert len(contents[0].parts) == 4
        assert contents[0].parts[0].text == "Analyze these documents:"
        assert contents[0].parts[1].file_data.mime_type == "application/pdf"
        assert contents[0].parts[2].file_data.mime_type == "text/plain"
        assert contents[0].parts[3].text == "What do you see?"

    def test_empty_content_after_filtering(self):
        """Test when all content is filtered out."""
        message = UserPromptMessage(
            content=[
                # Only unsupported content
                DocumentPromptMessageContent(
                    format="docx",
                    base64_data=base64.b64encode(b"test").decode(),
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            ]
        )

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):

            contents = self.llm._build_gemini_contents(
                prompt_messages=[message], genai_client=self.mock_client, config=self.config
            )

        # All content filtered out
        assert len(contents) == 1
        assert len(contents[0].parts) == 0

    def test_none_mime_type_handling(self):
        """Test handling of documents with None mime_type."""
        message = UserPromptMessage(
            content=[
                DocumentPromptMessageContent(
                    format="txt", base64_data=base64.b64encode(b"test").decode(), mime_type=""
                )
            ]
        )

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):

            contents = self.llm._build_gemini_contents(
                prompt_messages=[message], genai_client=self.mock_client, config=self.config
            )

        # Should handle gracefully
        assert len(contents) == 1

    def test_file_caching_mechanism(self):
        """Test that file uploads are cached properly."""
        # Clear cache and reset mock to ensure clean state
        self.memory_cache.clear()
        self.mock_client.reset_mock()

        # Reset mock file upload response
        self.mock_client.files.upload.return_value = self.mock_file
        self.mock_client.files.upload.side_effect = None  # Clear any side effects

        pdf_bytes = DocumentGenerator.create_pdf_bytes()
        base64_data = base64.b64encode(pdf_bytes).decode()

        content = DocumentPromptMessageContent(
            format="pdf", base64_data=base64_data, mime_type="application/pdf"
        )

        # Debug: Check if cache is truly empty
        cache_key = f"{content.type.value}:{hash(content.data)}"
        print(f"Cache key: {cache_key}")
        print(f"Cache exists before: {self.memory_cache.exists(cache_key)}")

        with patch("tempfile.NamedTemporaryFile"), patch("os.unlink"):

            # First upload - should call mock
            uri1, mime1 = self.llm._upload_file_content_to_google(content, self.mock_client)
            print(f"After first upload - call count: {self.mock_client.files.upload.call_count}")
            print(f"Cache exists after first: {self.memory_cache.exists(cache_key)}")

            # Second upload (should use cache)
            uri2, mime2 = self.llm._upload_file_content_to_google(content, self.mock_client)
            print(f"After second upload - call count: {self.mock_client.files.upload.call_count}")

        assert uri1 == uri2 == "gs://test-bucket/test-file"
        assert mime1 == mime2 == "application/pdf"

        # Should only upload once due to caching
        print(f"{self.mock_client.files.upload.call_count=}")
        assert self.mock_client.files.upload.call_count == 1


@pytest.mark.skipif(
    not os.getenv("GEMINI_API_KEY"), reason="GEMINI_API_KEY not found in environment"
)
class TestDocumentFilteringIntegration:
    """Integration tests with real Gemini API (requires API key)."""

    @classmethod
    def setup_class(cls):
        """Setup class-level fixtures."""
        cls.api_key = os.getenv("GEMINI_API_KEY")
        if not cls.api_key:
            pytest.skip("GEMINI_API_KEY not found")

    def setup_method(self):
        """Setup test fixtures."""
        self.llm = GoogleLargeLanguageModel([])

        # Validate credentials first
        try:
            self.llm.validate_credentials(
                model=GEMINI_TEST_CONFIG["model"], credentials={"google_api_key": self.api_key}
            )
        except Exception as e:
            pytest.skip(f"Invalid GEMINI_API_KEY: {e}")

        # Create real client
        self.client = genai.Client(api_key=self.api_key)

        self.model = GEMINI_TEST_CONFIG["model"]

        # Create minimal cost configuration
        self.config = types.GenerateContentConfig(
            max_output_tokens=GEMINI_TEST_CONFIG["max_output_tokens"],
            temperature=GEMINI_TEST_CONFIG["temperature"],
        )

        # Use memory cache for testing with integration test namespace
        self.memory_cache = MemoryFileCache(namespace="integration_test")

        # Patch the file cache for integration tests
        # Try different patch paths to handle different execution contexts
        self.cache_patcher = None
        for patch_path in ["models.llm.llm.file_cache", "llm.file_cache"]:
            try:
                self.cache_patcher = patch(patch_path, self.memory_cache)
                self.cache_patcher.start()
                break
            except (ImportError, AttributeError):
                if self.cache_patcher:
                    with suppress(Exception):
                        self.cache_patcher.stop()
                continue
        if not self.cache_patcher:
            # Fallback: patch the module directly
            import llm

            self.original_file_cache = llm.file_cache
            llm.file_cache = self.memory_cache

    def teardown_method(self):
        """Cleanup after each test."""
        if self.cache_patcher:
            with suppress(Exception):
                self.cache_patcher.stop()
        elif hasattr(self, "original_file_cache"):
            # Restore original file_cache if we patched it directly
            import llm

            llm.file_cache = self.original_file_cache

        self.memory_cache.clear()

    @pytest.mark.integration
    def test_real_pdf_upload_and_processing(self):
        """Test real PDF upload and processing with Gemini API."""
        pdf_bytes = DocumentGenerator.create_pdf_bytes()
        base64_data = base64.b64encode(pdf_bytes).decode()

        message = UserPromptMessage(
            content=[
                TextPromptMessageContent(data="Describe briefly:"),
                DocumentPromptMessageContent(
                    format="pdf", base64_data=base64_data, mime_type="application/pdf"
                ),
            ]
        )

        # Build contents with real upload
        contents = self.llm._build_gemini_contents(
            prompt_messages=[message], genai_client=self.client, config=self.config
        )

        # Verify upload succeeded
        assert len(contents) == 1
        assert len(contents[0].parts) == 2
        assert contents[0].parts[0].text == "Describe briefly:"
        assert (
            contents[0]
            .parts[1]
            .file_data.file_uri.startswith(
                "https://generativelanguage.googleapis.com/v1beta/files/"
            )
        )
        assert contents[0].parts[1].file_data.mime_type == "application/pdf"

        # Test actual generation
        response = self.client.models.generate_content(
            model=self.model, contents=contents, config=self.config
        )

        assert response.text  # Should get some response

    @pytest.mark.integration
    def test_real_text_document_upload(self):
        """Test real text document upload."""
        text_bytes = DocumentGenerator.create_text_bytes("This is a test document for analysis.")
        base64_data = base64.b64encode(text_bytes).decode()

        message = UserPromptMessage(
            content=[
                DocumentPromptMessageContent(
                    format="txt", base64_data=base64_data, mime_type="text/plain"
                ),
                TextPromptMessageContent(data="Summarize"),
            ]
        )

        contents = self.llm._build_gemini_contents(
            prompt_messages=[message], genai_client=self.client, config=self.config
        )

        # Verify upload
        assert len(contents) == 1
        assert len(contents[0].parts) == 2
        assert contents[0].parts[0].file_data.mime_type == "text/plain"
        assert contents[0].parts[1].text == "Summarize"

        # Test generation
        response = self.client.models.generate_content(
            model=self.model, contents=contents, config=self.config
        )

        assert response.text

    @pytest.mark.integration
    def test_real_markdown_document_upload(self):
        """Test real Markdown document upload."""
        md_bytes = DocumentGenerator.create_markdown_bytes(
            "# Test Document\n\nThis is a test markdown document."
        )
        base64_data = base64.b64encode(md_bytes).decode()

        message = UserPromptMessage(
            content=[
                DocumentPromptMessageContent(
                    format="md", base64_data=base64_data, mime_type="text/markdown"
                )
            ]
        )

        contents = self.llm._build_gemini_contents(
            prompt_messages=[message], genai_client=self.client, config=self.config
        )

        assert len(contents) == 1
        assert len(contents[0].parts) == 1
        assert contents[0].parts[0].file_data.mime_type == "text/markdown"

        # Test generation
        response = self.client.models.generate_content(
            model=self.model, contents=contents, config=self.config
        )

        assert response.text

    @pytest.mark.integration
    def test_real_filtering_with_mixed_documents(self):
        """Test real API with mixed supported/unsupported documents."""
        message = UserPromptMessage(
            content=[
                TextPromptMessageContent(data="Process docs:"),
                # Supported PDF
                DocumentPromptMessageContent(
                    format="pdf",
                    base64_data=base64.b64encode(DocumentGenerator.create_pdf_bytes()).decode(),
                    mime_type="application/pdf",
                ),
                # Unsupported DOCX (should be filtered)
                DocumentPromptMessageContent(
                    format="docx",
                    base64_data=base64.b64encode(DocumentGenerator.create_docx_bytes()).decode(),
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
                # Supported HTML
                DocumentPromptMessageContent(
                    format="html",
                    base64_data=base64.b64encode(DocumentGenerator.create_html_bytes()).decode(),
                    mime_type="text/html",
                ),
            ]
        )

        contents = self.llm._build_gemini_contents(
            prompt_messages=[message], genai_client=self.client, config=self.config
        )

        # Should have: text + PDF + HTML (DOCX filtered out)
        assert len(contents) == 1
        assert len(contents[0].parts) == 3
        assert contents[0].parts[0].text == "Process docs:"
        assert contents[0].parts[1].file_data.mime_type == "application/pdf"
        assert contents[0].parts[2].file_data.mime_type == "text/html"

        # Test generation works
        response = self.client.models.generate_content(
            model=self.model, contents=contents, config=self.config
        )

        assert response.text

    @pytest.mark.integration
    def test_real_unsupported_document_rejection(self):
        """Test that unsupported documents are properly filtered in real calls."""
        message = UserPromptMessage(
            content=[
                TextPromptMessageContent(data="Check this:"),
                # Only unsupported DOCX
                DocumentPromptMessageContent(
                    format="docx",
                    base64_data=base64.b64encode(DocumentGenerator.create_docx_bytes()).decode(),
                    mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            ]
        )

        contents = self.llm._build_gemini_contents(
            prompt_messages=[message], genai_client=self.client, config=self.config
        )

        # DOCX should be filtered, only text remains
        assert len(contents) == 1
        assert len(contents[0].parts) == 1
        assert contents[0].parts[0].text == "Check this:"

        # Can still generate with just text
        response = self.client.models.generate_content(
            model=self.model, contents=contents, config=self.config
        )

        assert response.text


# Configuration for pytest
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires API key)"
    )


# Run tests:
# All tests: pytest test_document_filtering.py -v
# Unit tests only: pytest test_document_filtering.py::TestDocumentFilteringUnit -v
# Integration tests only: pytest test_document_filtering.py::TestDocumentFilteringIntegration -v -m integration

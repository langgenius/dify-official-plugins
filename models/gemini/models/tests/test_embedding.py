"""
Unit tests for Gemini Text Embedding model.

These tests do NOT require Dify CLI or real API keys.
They test the internal logic using mocks.
"""

import base64
import time
from decimal import Decimal
from unittest.mock import MagicMock, Mock, patch

import pytest
from dify_plugin.entities.model.text_embedding import (
    EmbeddingUsage,
    MultiModalContent,
    MultiModalContentType,
    MultiModalEmbeddingResult,
)

try:
    from models.text_embedding.text_embedding import GeminiTextEmbeddingModel
except ImportError:
    import sys
    import os

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from models.text_embedding.text_embedding import GeminiTextEmbeddingModel


# ---- Test Data ----

# Minimal valid JPEG: FF D8 FF
JPEG_BYTES = b"\xFF\xD8\xFF\xE0" + b"\x00" * 20
JPEG_BASE64 = base64.b64encode(JPEG_BYTES).decode()

# Minimal valid PNG: 89 50 4E 47 0D 0A 1A 0A
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 20
PNG_BASE64 = base64.b64encode(PNG_BYTES).decode()

# GIF89a header
GIF_BYTES = b"GIF89a" + b"\x00" * 20
GIF_BASE64 = base64.b64encode(GIF_BYTES).decode()

# WebP: RIFF....WEBP
WEBP_BYTES = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 20
WEBP_BASE64 = base64.b64encode(WEBP_BYTES).decode()

# Unknown format
UNKNOWN_BYTES = b"\x00\x01\x02\x03" + b"\x00" * 20
UNKNOWN_BASE64 = base64.b64encode(UNKNOWN_BYTES).decode()


def _make_usage() -> EmbeddingUsage:
    """Create a valid EmbeddingUsage for testing."""
    return EmbeddingUsage(
        tokens=100,
        total_tokens=100,
        unit_price=Decimal("0.15"),
        price_unit=Decimal("0.000001"),
        total_price=Decimal("0.000015"),
        currency="USD",
        latency=0.1,
    )


@pytest.fixture
def embedding_model():
    """Create an embedding model instance for testing."""
    return GeminiTextEmbeddingModel([])


# ================================================================
# Test: _detect_image_mime_type
# ================================================================


class TestDetectImageMimeType:
    """Tests for image MIME type detection and format validation."""

    def setup_method(self):
        self.model = GeminiTextEmbeddingModel([])

    # ---- Detection tests ----

    def test_detect_jpeg(self):
        """JPEG bytes should be detected as image/jpeg"""
        assert self.model._detect_image_mime_type(JPEG_BASE64) == "image/jpeg"

    def test_detect_png(self):
        """PNG bytes should be detected as image/png"""
        assert self.model._detect_image_mime_type(PNG_BASE64) == "image/png"

    def test_detect_gif(self):
        """GIF bytes should be detected as image/gif"""
        assert self.model._detect_image_mime_type(GIF_BASE64) == "image/gif"

    def test_detect_webp(self):
        """WebP bytes should be detected as image/webp"""
        assert self.model._detect_image_mime_type(WEBP_BASE64) == "image/webp"

    def test_detect_unknown_defaults_to_jpeg(self):
        """Unknown format should default to image/jpeg"""
        assert self.model._detect_image_mime_type(UNKNOWN_BASE64) == "image/jpeg"

    def test_detect_with_data_uri_prefix(self):
        """Data URI prefix should be stripped before detection"""
        data_uri = f"data:image/png;base64,{PNG_BASE64}"
        assert self.model._detect_image_mime_type(data_uri) == "image/png"

    def test_detect_invalid_base64_raises_when_validate(self):
        """Invalid base64 input with validate_format=True should raise ValueError"""
        with pytest.raises(ValueError):
            self.model._detect_image_mime_type("not-valid-base64!!!", validate_format=True)

    def test_detect_invalid_base64_raises_without_validate(self):
        """Invalid base64 input raises ValueError (binascii.Error is a subclass of ValueError)"""
        # binascii.Error inherits from ValueError; the except ValueError: raise
        # clause re-raises it even when validate_format=False
        with pytest.raises(ValueError):
            self.model._detect_image_mime_type("not-valid-base64!!!")

    # ---- Validation tests (validate_format=True) ----

    def test_validate_jpeg_passes(self):
        """JPEG should pass format validation"""
        result = self.model._detect_image_mime_type(JPEG_BASE64, validate_format=True)
        assert result == "image/jpeg"

    def test_validate_png_passes(self):
        """PNG should pass format validation"""
        result = self.model._detect_image_mime_type(PNG_BASE64, validate_format=True)
        assert result == "image/png"

    def test_validate_gif_rejected(self):
        """GIF should be rejected when validation is enabled"""
        with pytest.raises(ValueError, match="Unsupported image format.*image/gif"):
            self.model._detect_image_mime_type(GIF_BASE64, validate_format=True)

    def test_validate_webp_rejected(self):
        """WebP should be rejected when validation is enabled"""
        with pytest.raises(ValueError, match="Unsupported image format.*image/webp"):
            self.model._detect_image_mime_type(WEBP_BASE64, validate_format=True)

    def test_validate_false_allows_all_formats(self):
        """All formats should be allowed when validate_format=False (default)"""
        # GIF and WebP should NOT raise
        assert (
            self.model._detect_image_mime_type(GIF_BASE64, validate_format=False)
            == "image/gif"
        )
        assert (
            self.model._detect_image_mime_type(WEBP_BASE64, validate_format=False)
            == "image/webp"
        )


# ================================================================
# Test: _get_output_dimension
# ================================================================


class TestGetOutputDimension:
    """Tests for reading output_dimension from model schema."""

    def setup_method(self):
        self.model = GeminiTextEmbeddingModel([])

    def test_returns_dimension_when_configured(self):
        """Should return output_dimension value from model properties"""
        mock_schema = Mock()
        mock_schema.model_properties = {"output_dimension": 768}

        with patch.object(self.model, "get_model_schema", return_value=mock_schema):
            result = self.model._get_output_dimension("test-model", {})
            assert result == 768

    def test_returns_none_when_not_configured(self):
        """Should return None when output_dimension is not in model properties"""
        mock_schema = Mock()
        mock_schema.model_properties = {"context_size": 8192}

        with patch.object(self.model, "get_model_schema", return_value=mock_schema):
            result = self.model._get_output_dimension("test-model", {})
            assert result is None

    def test_returns_none_when_schema_is_none(self):
        """Should return None when model schema cannot be loaded"""
        with patch.object(self.model, "get_model_schema", return_value=None):
            result = self.model._get_output_dimension("test-model", {})
            assert result is None

    def test_returns_none_on_exception(self):
        """Should return None when get_model_schema throws"""
        with patch.object(
            self.model, "get_model_schema", side_effect=Exception("err")
        ):
            result = self.model._get_output_dimension("test-model", {})
            assert result is None

    @pytest.mark.parametrize("dimension", [3072, 1536, 768])
    def test_returns_various_mrl_dimensions(self, dimension):
        """Should correctly return MRL-supported dimensions (3072, 1536, 768)"""
        mock_schema = Mock()
        mock_schema.model_properties = {"output_dimension": dimension}

        with patch.object(self.model, "get_model_schema", return_value=mock_schema):
            result = self.model._get_output_dimension("test-model", {})
            assert result == dimension


# ================================================================
# Test: _invoke_multimodal — image count limit per batch
# ================================================================


class TestMultimodalImageCountLimit:
    """Tests for per-batch image count validation in _invoke_multimodal."""

    def setup_method(self):
        self.model = GeminiTextEmbeddingModel([])
        self.credentials = {"google_api_key": "fake-key"}

    @patch("models.text_embedding.text_embedding.genai")
    def test_6_images_passes(self, mock_genai):
        """Exactly 6 images in a single batch should pass"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_embedding = Mock()
        mock_embedding.values = [0.1] * 10
        mock_embedding.statistics = Mock()
        mock_embedding.statistics.token_count = 50
        mock_response = Mock()
        mock_response.embeddings = [mock_embedding] * 6
        mock_client.models.embed_content.return_value = mock_response

        usage = _make_usage()

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=None), \
             patch.object(self.model, "_calc_response_usage", return_value=usage):

            documents = [
                MultiModalContent(
                    content_type=MultiModalContentType.IMAGE,
                    content=JPEG_BASE64,
                )
                for _ in range(6)
            ]

            result = self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=documents,
            )
            assert len(result.embeddings) == 6

    @patch("models.text_embedding.text_embedding.genai")
    def test_7_images_in_single_batch_raises(self, mock_genai):
        """More than 6 images in a single batch should raise ValueError"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=None):

            documents = [
                MultiModalContent(
                    content_type=MultiModalContentType.IMAGE,
                    content=JPEG_BASE64,
                )
                for _ in range(7)
            ]

            with pytest.raises(ValueError, match="Too many images in batch"):
                self.model._invoke_multimodal(
                    model="gemini-embedding-2-preview",
                    credentials=self.credentials,
                    documents=documents,
                )

    @patch("models.text_embedding.text_embedding.genai")
    def test_images_spread_across_batches_passes(self, mock_genai):
        """Images split into batches of <=6 each should all pass"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_embedding = Mock()
        mock_embedding.values = [0.1] * 10
        mock_embedding.statistics = Mock()
        mock_embedding.statistics.token_count = 50

        # Each batch call returns embeddings matching batch size
        def side_effect_embed(**kwargs):
            batch_size = len(kwargs.get("contents", []))
            resp = Mock()
            resp.embeddings = [mock_embedding] * batch_size
            return resp

        mock_client.models.embed_content.side_effect = side_effect_embed

        usage = _make_usage()

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=5), \
             patch.object(self.model, "_get_output_dimension", return_value=None), \
             patch.object(self.model, "_calc_response_usage", return_value=usage):

            # 8 images, max_chunks=5 → batch1: 5 images, batch2: 3 images, both <=6
            documents = [
                MultiModalContent(
                    content_type=MultiModalContentType.IMAGE,
                    content=JPEG_BASE64,
                )
                for _ in range(8)
            ]

            result = self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=documents,
            )
            assert len(result.embeddings) == 8

    @patch("models.text_embedding.text_embedding.genai")
    def test_mixed_text_images_within_limit(self, mock_genai):
        """Mixed text + images should only count images toward the limit"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_embedding = Mock()
        mock_embedding.values = [0.1] * 10
        mock_embedding.statistics = Mock()
        mock_embedding.statistics.token_count = 30

        mock_response = Mock()
        mock_response.embeddings = [mock_embedding] * 8  # 6 images + 2 texts
        mock_client.models.embed_content.return_value = mock_response

        usage = _make_usage()

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=None), \
             patch.object(self.model, "_calc_response_usage", return_value=usage):

            documents = [
                MultiModalContent(
                    content_type=MultiModalContentType.TEXT, content="text1"
                ),
            ] + [
                MultiModalContent(
                    content_type=MultiModalContentType.IMAGE,
                    content=JPEG_BASE64,
                )
                for _ in range(6)
            ] + [
                MultiModalContent(
                    content_type=MultiModalContentType.TEXT, content="text2"
                ),
            ]

            result = self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=documents,
            )
            # 6 images + 2 texts = 8 total, all in one batch
            assert len(result.embeddings) == 8


# ================================================================
# Test: _invoke_multimodal — image format validation
# ================================================================


class TestMultimodalImageFormatValidation:
    """Tests for image format validation in _invoke_multimodal."""

    def setup_method(self):
        self.model = GeminiTextEmbeddingModel([])
        self.credentials = {"google_api_key": "fake-key"}

    @patch("models.text_embedding.text_embedding.genai")
    def test_gif_image_rejected(self, mock_genai):
        """GIF images should be rejected in multimodal embedding"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        doc = MultiModalContent(
            content_type=MultiModalContentType.IMAGE, content=GIF_BASE64
        )

        with pytest.raises(ValueError, match="Unsupported image format"):
            self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=[doc],
            )

    @patch("models.text_embedding.text_embedding.genai")
    def test_webp_image_rejected(self, mock_genai):
        """WebP images should be rejected in multimodal embedding"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        doc = MultiModalContent(
            content_type=MultiModalContentType.IMAGE, content=WEBP_BASE64
        )

        with pytest.raises(ValueError, match="Unsupported image format"):
            self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=[doc],
            )

    @patch("models.text_embedding.text_embedding.genai")
    def test_jpeg_image_accepted(self, mock_genai):
        """JPEG images should be accepted"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_embedding = Mock()
        mock_embedding.values = [0.1] * 10
        mock_embedding.statistics = Mock()
        mock_embedding.statistics.token_count = 50
        mock_response = Mock()
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response

        usage = _make_usage()

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=None), \
             patch.object(self.model, "_calc_response_usage", return_value=usage):

            doc = MultiModalContent(
                content_type=MultiModalContentType.IMAGE, content=JPEG_BASE64
            )

            result = self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=[doc],
            )
            assert len(result.embeddings) == 1

    @patch("models.text_embedding.text_embedding.genai")
    def test_png_image_accepted(self, mock_genai):
        """PNG images should be accepted"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_embedding = Mock()
        mock_embedding.values = [0.1] * 10
        mock_embedding.statistics = Mock()
        mock_embedding.statistics.token_count = 50
        mock_response = Mock()
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response

        usage = _make_usage()

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=None), \
             patch.object(self.model, "_calc_response_usage", return_value=usage):

            doc = MultiModalContent(
                content_type=MultiModalContentType.IMAGE, content=PNG_BASE64
            )

            result = self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=[doc],
            )
            assert len(result.embeddings) == 1


# ================================================================
# Test: _invoke_multimodal — mixed content (text + images)
# ================================================================


class TestMultimodalMixedContent:
    """Tests for mixed text + image content in _invoke_multimodal."""

    def setup_method(self):
        self.model = GeminiTextEmbeddingModel([])
        self.credentials = {"google_api_key": "fake-key"}

    @patch("models.text_embedding.text_embedding.genai")
    def test_mixed_text_and_images(self, mock_genai):
        """Mixed text and image content should work correctly"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_embedding = Mock()
        mock_embedding.values = [0.1, 0.2, 0.3]
        mock_embedding.statistics = Mock()
        mock_embedding.statistics.token_count = 30

        mock_response = Mock()
        mock_response.embeddings = [mock_embedding] * 3
        mock_client.models.embed_content.return_value = mock_response

        usage = _make_usage()

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=None), \
             patch.object(self.model, "_calc_response_usage", return_value=usage):

            documents = [
                MultiModalContent(
                    content_type=MultiModalContentType.TEXT, content="Hello world"
                ),
                MultiModalContent(
                    content_type=MultiModalContentType.IMAGE, content=JPEG_BASE64
                ),
                MultiModalContent(
                    content_type=MultiModalContentType.TEXT, content="Another text"
                ),
            ]

            result = self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=documents,
            )
            assert len(result.embeddings) == 3
            mock_client.models.embed_content.assert_called_once()

    @patch("models.text_embedding.text_embedding.genai")
    def test_text_only_via_multimodal(self, mock_genai):
        """Pure text documents should work via multimodal path"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_embedding = Mock()
        mock_embedding.values = [0.5, 0.6]
        mock_embedding.statistics = Mock()
        mock_embedding.statistics.token_count = 15
        mock_response = Mock()
        mock_response.embeddings = [mock_embedding] * 2
        mock_client.models.embed_content.return_value = mock_response

        usage = _make_usage()

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=None), \
             patch.object(self.model, "_calc_response_usage", return_value=usage):

            documents = [
                MultiModalContent(
                    content_type=MultiModalContentType.TEXT, content="Hello"
                ),
                MultiModalContent(
                    content_type=MultiModalContentType.TEXT, content="World"
                ),
            ]

            result = self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=documents,
            )
            assert len(result.embeddings) == 2


# ================================================================
# Test: _invoke_multimodal — output dimension config
# ================================================================


class TestMultimodalOutputDimension:
    """Tests for output_dimension (MRL) configuration in _invoke_multimodal."""

    def setup_method(self):
        self.model = GeminiTextEmbeddingModel([])
        self.credentials = {"google_api_key": "fake-key"}

    @patch("models.text_embedding.text_embedding.genai")
    def test_output_dimension_passed_to_config(self, mock_genai):
        """output_dimension should be set in EmbedContentConfig when configured"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_embedding = Mock()
        mock_embedding.values = [0.1] * 768
        mock_embedding.statistics = Mock()
        mock_embedding.statistics.token_count = 10
        mock_response = Mock()
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response

        usage = _make_usage()

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=768), \
             patch.object(self.model, "_calc_response_usage", return_value=usage):

            documents = [
                MultiModalContent(
                    content_type=MultiModalContentType.TEXT, content="test"
                ),
            ]

            self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=documents,
            )

            # Verify embed_content was called with output_dimensionality in config
            call_kwargs = mock_client.models.embed_content.call_args
            config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
            assert config is not None
            assert config.output_dimensionality == 768

    @patch("models.text_embedding.text_embedding.genai")
    def test_no_output_dimension_when_not_configured(self, mock_genai):
        """output_dimension should NOT be set when model has no configured dimension"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_embedding = Mock()
        mock_embedding.values = [0.1] * 3072
        mock_embedding.statistics = Mock()
        mock_embedding.statistics.token_count = 10
        mock_response = Mock()
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response

        usage = _make_usage()

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=None), \
             patch.object(self.model, "_calc_response_usage", return_value=usage):

            documents = [
                MultiModalContent(
                    content_type=MultiModalContentType.TEXT, content="test"
                ),
            ]

            self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=documents,
            )

            # Verify embed_content was called, config should not have output_dimensionality
            call_kwargs = mock_client.models.embed_content.call_args
            config = call_kwargs.kwargs.get("config") or call_kwargs[1].get("config")
            if config is not None:
                assert (
                    not hasattr(config, "output_dimensionality")
                    or config.output_dimensionality is None
                )


# ================================================================
# Test: _invoke_multimodal — token counting fallback
# ================================================================


class TestMultimodalTokenCounting:
    """Tests for token counting logic in _invoke_multimodal."""

    def setup_method(self):
        self.model = GeminiTextEmbeddingModel([])
        self.credentials = {"google_api_key": "fake-key"}

    @patch("models.text_embedding.text_embedding.genai")
    def test_uses_token_count_from_statistics(self, mock_genai):
        """Should use token_count from response statistics when available"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_embedding = Mock()
        mock_embedding.values = [0.1] * 10
        mock_embedding.statistics = Mock()
        mock_embedding.statistics.token_count = 42

        mock_response = Mock()
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response

        usage = _make_usage()

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=None), \
             patch.object(self.model, "_calc_response_usage", return_value=usage) as mock_calc:

            documents = [
                MultiModalContent(
                    content_type=MultiModalContentType.TEXT, content="test"
                ),
            ]

            self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=documents,
            )

            # _calc_response_usage should be called with tokens=42
            mock_calc.assert_called_once_with(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                tokens=42,
            )

    @patch("models.text_embedding.text_embedding.genai")
    def test_image_fallback_uses_image_token_estimate(self, mock_genai):
        """Image without statistics should use IMAGE_TOKEN_ESTIMATE (258)"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_embedding = Mock()
        mock_embedding.values = [0.1] * 10
        mock_embedding.statistics = None  # No statistics

        mock_response = Mock()
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response

        usage = _make_usage()

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=None), \
             patch.object(self.model, "_calc_response_usage", return_value=usage) as mock_calc:

            documents = [
                MultiModalContent(
                    content_type=MultiModalContentType.IMAGE, content=JPEG_BASE64
                ),
            ]

            self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=documents,
            )

            # Should use IMAGE_TOKEN_ESTIMATE (258) for image fallback
            mock_calc.assert_called_once_with(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                tokens=GeminiTextEmbeddingModel.IMAGE_TOKEN_ESTIMATE,
            )

    @patch("models.text_embedding.text_embedding.genai")
    def test_text_fallback_uses_gpt2_tokenizer(self, mock_genai):
        """Text without statistics should use GPT-2 tokenizer estimation"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_embedding = Mock()
        mock_embedding.values = [0.1] * 10
        mock_embedding.statistics = None  # No statistics

        mock_response = Mock()
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response

        usage = _make_usage()
        test_text = "Hello, this is a test sentence for token estimation."

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=None), \
             patch.object(self.model, "_calc_response_usage", return_value=usage) as mock_calc, \
             patch.object(self.model, "_get_num_tokens_by_gpt2", return_value=12) as mock_gpt2:

            documents = [
                MultiModalContent(
                    content_type=MultiModalContentType.TEXT, content=test_text
                ),
            ]

            self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=documents,
            )

            # GPT-2 tokenizer should be called with the original text
            mock_gpt2.assert_called_once_with(test_text)
            # _calc_response_usage should be called with the GPT-2 estimated tokens
            mock_calc.assert_called_once_with(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                tokens=12,
            )

    @patch("models.text_embedding.text_embedding.genai")
    def test_mixed_content_fallback_tokens(self, mock_genai):
        """Mixed text+image without statistics should use correct estimation per type"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_embedding = Mock()
        mock_embedding.values = [0.1] * 10
        mock_embedding.statistics = None  # No statistics

        mock_response = Mock()
        mock_response.embeddings = [mock_embedding, mock_embedding, mock_embedding]
        mock_client.models.embed_content.return_value = mock_response

        usage = _make_usage()
        text1 = "First text"
        text2 = "Second text"

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=None), \
             patch.object(self.model, "_calc_response_usage", return_value=usage) as mock_calc, \
             patch.object(self.model, "_get_num_tokens_by_gpt2", return_value=5) as mock_gpt2:

            documents = [
                MultiModalContent(content_type=MultiModalContentType.TEXT, content=text1),
                MultiModalContent(content_type=MultiModalContentType.IMAGE, content=JPEG_BASE64),
                MultiModalContent(content_type=MultiModalContentType.TEXT, content=text2),
            ]

            self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=documents,
            )

            # Expected: text1(5) + image(258) + text2(5) = 268
            expected_tokens = 5 + GeminiTextEmbeddingModel.IMAGE_TOKEN_ESTIMATE + 5
            mock_calc.assert_called_once_with(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                tokens=expected_tokens,
            )
            # GPT-2 should be called twice (once per text)
            assert mock_gpt2.call_count == 2

    @patch("models.text_embedding.text_embedding.genai")
    def test_statistics_takes_priority_over_fallback(self, mock_genai):
        """When statistics are available, they should be used instead of fallback"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        # Embedding with statistics
        mock_emb_with_stats = Mock()
        mock_emb_with_stats.values = [0.1] * 10
        mock_emb_with_stats.statistics = Mock()
        mock_emb_with_stats.statistics.token_count = 100

        # Embedding without statistics
        mock_emb_no_stats = Mock()
        mock_emb_no_stats.values = [0.2] * 10
        mock_emb_no_stats.statistics = None

        mock_response = Mock()
        mock_response.embeddings = [mock_emb_with_stats, mock_emb_no_stats]
        mock_client.models.embed_content.return_value = mock_response

        usage = _make_usage()

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=None), \
             patch.object(self.model, "_calc_response_usage", return_value=usage) as mock_calc, \
             patch.object(self.model, "_get_num_tokens_by_gpt2", return_value=7):

            documents = [
                MultiModalContent(content_type=MultiModalContentType.TEXT, content="has stats"),
                MultiModalContent(content_type=MultiModalContentType.TEXT, content="no stats"),
            ]

            self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=documents,
            )

            # First uses statistics (100), second uses GPT-2 fallback (7)
            mock_calc.assert_called_once_with(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                tokens=107,
            )


# ================================================================
# Test: _invoke_multimodal — empty embeddings error
# ================================================================


class TestMultimodalEmptyEmbeddings:
    """Tests for error handling when API returns no embeddings."""

    def setup_method(self):
        self.model = GeminiTextEmbeddingModel([])
        self.credentials = {"google_api_key": "fake-key"}

    @patch("models.text_embedding.text_embedding.genai")
    def test_raises_on_null_embeddings(self, mock_genai):
        """Should raise InvokeError when API returns null embeddings"""
        from dify_plugin.errors.model import InvokeError

        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_response = Mock()
        mock_response.embeddings = None
        mock_client.models.embed_content.return_value = mock_response

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=None):

            documents = [
                MultiModalContent(
                    content_type=MultiModalContentType.TEXT, content="test"
                ),
            ]

            with pytest.raises(InvokeError, match="Unable to get embeddings"):
                self.model._invoke_multimodal(
                    model="gemini-embedding-2-preview",
                    credentials=self.credentials,
                    documents=documents,
                )


# ================================================================
# Test: _invoke_multimodal — data URI prefix handling
# ================================================================


class TestMultimodalDataURIHandling:
    """Tests for base64 data URI prefix stripping in image processing."""

    def setup_method(self):
        self.model = GeminiTextEmbeddingModel([])
        self.credentials = {"google_api_key": "fake-key"}

    @patch("models.text_embedding.text_embedding.genai")
    def test_data_uri_prefix_stripped(self, mock_genai):
        """Image content with data URI prefix should be handled correctly"""
        mock_client = Mock()
        mock_genai.Client.return_value = mock_client

        mock_embedding = Mock()
        mock_embedding.values = [0.1] * 10
        mock_embedding.statistics = Mock()
        mock_embedding.statistics.token_count = 50
        mock_response = Mock()
        mock_response.embeddings = [mock_embedding]
        mock_client.models.embed_content.return_value = mock_response

        usage = _make_usage()

        with patch.object(self.model, "_get_context_size", return_value=8192), \
             patch.object(self.model, "_get_max_chunks", return_value=100), \
             patch.object(self.model, "_get_output_dimension", return_value=None), \
             patch.object(self.model, "_calc_response_usage", return_value=usage):

            # Image content with data URI prefix
            data_uri_content = f"data:image/jpeg;base64,{JPEG_BASE64}"

            doc = MultiModalContent(
                content_type=MultiModalContentType.IMAGE,
                content=data_uri_content,
            )

            result = self.model._invoke_multimodal(
                model="gemini-embedding-2-preview",
                credentials=self.credentials,
                documents=[doc],
            )
            assert len(result.embeddings) == 1


# ================================================================
# Test: Class-level constants
# ================================================================


class TestModelConstants:
    """Tests for modality-specific constants defined on the model class."""

    def test_max_images_per_request(self):
        assert GeminiTextEmbeddingModel.MAX_IMAGES_PER_REQUEST == 6

    def test_supported_image_formats(self):
        assert GeminiTextEmbeddingModel.SUPPORTED_IMAGE_FORMATS == {
            "image/jpeg",
            "image/png",
        }

    def test_supported_formats_excludes_gif(self):
        assert "image/gif" not in GeminiTextEmbeddingModel.SUPPORTED_IMAGE_FORMATS

    def test_supported_formats_excludes_webp(self):
        assert "image/webp" not in GeminiTextEmbeddingModel.SUPPORTED_IMAGE_FORMATS

    def test_image_token_estimate(self):
        assert GeminiTextEmbeddingModel.IMAGE_TOKEN_ESTIMATE == 258

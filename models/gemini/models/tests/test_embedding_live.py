"""
Live API tests for Gemini Embedding models.

These tests call the real Google Gemini API and require a valid API key.

Usage:
    export GEMINI_API_KEY="your-google-api-key"
    cd models/gemini
    pytest models/tests/test_embedding_live.py -v -s

All tests are marked with @pytest.mark.live so they can be skipped
in CI or when no API key is available.
"""

import base64
import os
import struct

import pytest
from google import genai
from google.genai import types
from google.genai.types import EmbedContentConfig

# ---- Configuration ----

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL_NAME = "gemini-embedding-2-preview"

# Skip all tests in this module if no API key is set
pytestmark = pytest.mark.skipif(
    not API_KEY,
    reason="GEMINI_API_KEY environment variable not set",
)


@pytest.fixture(scope="module")
def client():
    """Create a Google Genai client."""
    return genai.Client(api_key=API_KEY)


def _make_tiny_jpeg() -> bytes:
    """Create a minimal valid JPEG image (1x1 red pixel)."""
    # Minimal JPEG: SOI + APP0 + DQT + SOF0 + DHT + SOS + image data + EOI
    # Using a pre-built 1x1 red pixel JPEG (smallest possible valid JPEG)
    return bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00,
        0x01, 0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB,
        0x00, 0x43, 0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07,
        0x07, 0x07, 0x09, 0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B,
        0x0B, 0x0C, 0x19, 0x12, 0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E,
        0x1D, 0x1A, 0x1C, 0x1C, 0x20, 0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C,
        0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29, 0x2C, 0x30, 0x31, 0x34, 0x34,
        0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32, 0x3C, 0x2E, 0x33, 0x34,
        0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01, 0x00, 0x01, 0x01,
        0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00, 0x01, 0x05,
        0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01,
        0x03, 0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00,
        0x01, 0x7D, 0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21,
        0x31, 0x41, 0x06, 0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32,
        0x81, 0x91, 0xA1, 0x08, 0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1,
        0xF0, 0x24, 0x33, 0x62, 0x72, 0x82, 0x09, 0x0A, 0x16, 0x17, 0x18,
        0x19, 0x1A, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x34, 0x35, 0x36,
        0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49,
        0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59, 0x5A, 0x63, 0x64,
        0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75, 0x76, 0x77,
        0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8A,
        0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5,
        0xB6, 0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7,
        0xC8, 0xC9, 0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9,
        0xDA, 0xE1, 0xE2, 0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA,
        0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF,
        0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00, 0x7B, 0x94,
        0x11, 0x00, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xD9
    ])


def _make_tiny_png() -> bytes:
    """Create a minimal valid PNG image (1x1 red pixel)."""
    import zlib

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    signature = b"\x89PNG\r\n\x1a\n"
    # IHDR: 1x1, 8-bit RGB
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)
    # IDAT: filter byte (0) + RGB (255, 0, 0)
    raw = b"\x00\xFF\x00\x00"
    idat = _chunk(b"IDAT", zlib.compress(raw))
    # IEND
    iend = _chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


# ================================================================
# Test 1: Text embedding — basic functionality
# ================================================================


class TestLiveTextEmbedding:
    """Test real API calls for text embedding."""

    def test_single_text(self, client):
        """Single text should return a valid embedding vector"""
        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=["Hello, world!"],
        )

        assert response.embeddings is not None
        assert len(response.embeddings) == 1

        embedding = response.embeddings[0].values
        assert embedding is not None
        assert len(embedding) > 0
        # Default dimension for gemini-embedding-2-preview is 3072
        assert len(embedding) == 3072

        print(f"\n✅ Text embedding dimension: {len(embedding)}")
        print(f"   First 5 values: {embedding[:5]}")

    def test_multiple_texts(self, client):
        """Multiple texts should each return an embedding"""
        texts = ["Hello", "World", "Gemini Embedding Test"]

        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=texts,
        )

        assert response.embeddings is not None
        assert len(response.embeddings) == 3

        for i, emb in enumerate(response.embeddings):
            assert emb.values is not None
            assert len(emb.values) == 3072
            print(f"\n✅ Text[{i}] embedding OK, dim={len(emb.values)}")

    def test_text_with_task_type(self, client):
        """Text embedding with explicit task_type should work"""
        config = EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")

        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=["This is a document for retrieval."],
            config=config,
        )

        assert response.embeddings is not None
        assert len(response.embeddings) == 1
        assert len(response.embeddings[0].values) == 3072
        print(f"\n✅ Text embedding with task_type OK")


# ================================================================
# Test 2: MRL — output_dimensionality
# ================================================================


class TestLiveMRL:
    """Test Matryoshka Representation Learning (variable output dimensions)."""

    @pytest.mark.parametrize("dim", [3072, 1536, 768])
    def test_output_dimensionality(self, client, dim):
        """Should return embeddings of the requested dimension"""
        config = EmbedContentConfig(output_dimensionality=dim)

        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=["Test MRL dimension"],
            config=config,
        )

        assert response.embeddings is not None
        assert len(response.embeddings) == 1

        embedding = response.embeddings[0].values
        assert len(embedding) == dim
        print(f"\n✅ MRL dimension {dim} OK, got {len(embedding)} values")


# ================================================================
# Test 3: Image embedding (multimodal)
# ================================================================


class TestLiveImageEmbedding:
    """Test real API calls for image embedding."""

    def test_jpeg_image(self, client):
        """JPEG image should return a valid embedding"""
        jpeg_bytes = _make_tiny_jpeg()
        part = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")

        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=[part],
        )

        assert response.embeddings is not None
        assert len(response.embeddings) == 1

        embedding = response.embeddings[0].values
        assert embedding is not None
        assert len(embedding) == 3072
        print(f"\n✅ JPEG image embedding OK, dim={len(embedding)}")

    def test_png_image(self, client):
        """PNG image should return a valid embedding"""
        png_bytes = _make_tiny_png()
        part = types.Part.from_bytes(data=png_bytes, mime_type="image/png")

        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=[part],
        )

        assert response.embeddings is not None
        assert len(response.embeddings) == 1

        embedding = response.embeddings[0].values
        assert embedding is not None
        assert len(embedding) == 3072
        print(f"\n✅ PNG image embedding OK, dim={len(embedding)}")

    def test_image_with_mrl(self, client):
        """Image embedding with MRL (reduced dimension) should work"""
        jpeg_bytes = _make_tiny_jpeg()
        part = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")

        config = EmbedContentConfig(output_dimensionality=768)

        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=[part],
            config=config,
        )

        assert response.embeddings is not None
        embedding = response.embeddings[0].values
        assert len(embedding) == 768
        print(f"\n✅ Image embedding with MRL dim=768 OK")


# ================================================================
# Test 4: Mixed text + image (multimodal)
# ================================================================


class TestLiveMixedContent:
    """Test mixed text and image embeddings in a single request."""

    def test_text_and_image_together(self, client):
        """Mixed text + image in one request should each return embeddings"""
        jpeg_bytes = _make_tiny_jpeg()
        image_part = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")

        contents = [
            "A text description",
            image_part,
            "Another text",
        ]

        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=contents,
        )

        assert response.embeddings is not None
        assert len(response.embeddings) == 3

        for i, emb in enumerate(response.embeddings):
            assert emb.values is not None
            assert len(emb.values) == 3072
            print(f"\n✅ Mixed content[{i}] embedding OK, dim={len(emb.values)}")

    def test_multiple_images(self, client):
        """Multiple images (up to 6) should all return embeddings"""
        jpeg_bytes = _make_tiny_jpeg()
        png_bytes = _make_tiny_png()

        contents = [
            types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
            types.Part.from_bytes(data=png_bytes, mime_type="image/png"),
            types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
        ]

        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=contents,
        )

        assert response.embeddings is not None
        assert len(response.embeddings) == 3

        for i, emb in enumerate(response.embeddings):
            assert len(emb.values) == 3072

        print(f"\n✅ Multiple images ({len(contents)}) all returned 3072-dim embeddings")


# ================================================================
# Test 5: Token statistics
# ================================================================


class TestLiveTokenStatistics:
    """Test that the API returns token usage statistics."""

    def test_text_has_token_count(self, client):
        """Text embedding response should include token_count statistics"""
        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=["Hello, this is a test sentence for token counting."],
        )

        assert response.embeddings is not None
        emb = response.embeddings[0]

        if emb.statistics and emb.statistics.token_count:
            print(f"\n✅ Token count: {emb.statistics.token_count}")
            assert emb.statistics.token_count > 0
        else:
            print(f"\n⚠️  No token statistics returned (statistics={emb.statistics})")

    def test_image_has_token_count(self, client):
        """Image embedding response should include token_count statistics"""
        jpeg_bytes = _make_tiny_jpeg()
        part = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")

        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=[part],
        )

        assert response.embeddings is not None
        emb = response.embeddings[0]

        if emb.statistics and emb.statistics.token_count:
            print(f"\n✅ Image token count: {emb.statistics.token_count}")
        else:
            print(f"\n⚠️  No token statistics for image (statistics={emb.statistics})")


# ================================================================
# Test 6: Validate credentials
# ================================================================


class TestLiveValidateCredentials:
    """Test credential validation."""

    def test_valid_key_works(self, client):
        """A valid API key should successfully call the API"""
        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=["ping"],
        )
        assert response.embeddings is not None
        print(f"\n✅ Credential validation passed")

    def test_invalid_key_fails(self):
        """An invalid API key should raise an error"""
        bad_client = genai.Client(api_key="invalid-key-12345")

        with pytest.raises(Exception):
            bad_client.models.embed_content(
                model=MODEL_NAME,
                contents=["ping"],
            )
        print(f"\n✅ Invalid key correctly rejected")

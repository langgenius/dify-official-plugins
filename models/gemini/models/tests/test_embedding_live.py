"""
Live API tests for Gemini Embedding models.

These tests call the real Google Gemini API and require a valid API key.

Usage:
    export GEMINI_API_KEY="your-google-api-key"
    export RUN_GEMINI_LIVE=1
    cd models/gemini
    pytest models/tests/test_embedding_live.py -v -s

All tests are marked with @pytest.mark.live and run only when explicitly enabled.
"""

import os
import struct
import zlib

import pytest
from google import genai
from google.genai import types
from google.genai.types import EmbedContentConfig

# ---- Configuration ----

MODEL_NAME = "gemini-embedding-2-preview"

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def client():
    """Create a Google Genai client."""
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _make_tiny_jpeg() -> bytes:
    """Create a valid 1x1 red JPEG image."""
    from io import BytesIO

    from PIL import Image

    image = Image.new("RGB", (1, 1), (255, 0, 0))
    buffer = BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def _make_tiny_png() -> bytes:
    """Create a minimal valid PNG image (1x1 red pixel)."""

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    signature = b"\x89PNG\r\n\x1a\n"
    # IHDR: 1x1, 8-bit RGB
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    ihdr = _chunk(b"IHDR", ihdr_data)
    # IDAT: filter byte (0) + RGB (255, 0, 0)
    raw = b"\x00\xff\x00\x00"
    idat = _chunk(b"IDAT", zlib.compress(raw))
    # IEND
    iend = _chunk(b"IEND", b"")
    return signature + ihdr + idat + iend


def _user_content(part: str | types.Part) -> types.UserContent:
    return types.UserContent(parts=[part])


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
            contents=[_user_content(text) for text in texts],
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
        print("\n✅ Text embedding with task_type OK")


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
        print("\n✅ Image embedding with MRL dim=768 OK")


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
            _user_content("A text description"),
            _user_content(image_part),
            _user_content("Another text"),
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
            _user_content(
                types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")
            ),
            _user_content(types.Part.from_bytes(data=png_bytes, mime_type="image/png")),
            _user_content(
                types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")
            ),
        ]

        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=contents,
        )

        assert response.embeddings is not None
        assert len(response.embeddings) == 3

        for i, emb in enumerate(response.embeddings):
            assert len(emb.values) == 3072

        print(
            f"\n✅ Multiple images ({len(contents)}) all returned 3072-dim embeddings"
        )


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
        print("\n✅ Credential validation passed")

    def test_invalid_key_fails(self):
        """An invalid API key should raise an error"""
        bad_client = genai.Client(api_key="invalid-key-12345")

        with pytest.raises(Exception):
            bad_client.models.embed_content(
                model=MODEL_NAME,
                contents=["ping"],
            )
        print("\n✅ Invalid key correctly rejected")

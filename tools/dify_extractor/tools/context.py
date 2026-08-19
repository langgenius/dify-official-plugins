from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tools.image_assets import ImageAssetService


@dataclass(frozen=True, slots=True)
class ExtractionContext:
    """Shared immutable inputs for a single extraction."""

    file_bytes: bytes
    file_name: str
    file_extension: str
    mime_type: str | None = None
    image_service: "ImageAssetService | None" = None

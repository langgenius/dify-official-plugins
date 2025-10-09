from enum import StrEnum
from typing import Optional, Literal

from pydantic import BaseModel


class PreProcessingRule(BaseModel):
    id: str
    enabled: bool


class Segmentation(BaseModel):
    separator: str = "\n"
    max_tokens: int
    chunk_overlap: int = 0


class Rule(BaseModel):
    segmentation: Optional[Segmentation] = None
    parent_mode: Optional[Literal["full-doc", "paragraph"]] = None
    subchunk_segmentation: Optional[Segmentation] = None
    remove_extra_spaces: bool = False
    remove_urls_emails: bool = False


class ParentMode(StrEnum):
    FULL_DOC = "full_doc"
    PARAGRAPH = "paragraph"


class ParentChildChunk(BaseModel):
    """
    Parent Child Chunk.
    """

    parent_content: str
    child_contents: list[str]
    parent_mode: Literal["full-doc", "paragraph"] = "paragraph"


class ParentChildStructureChunk(BaseModel):
    """
    Parent Child Structure Chunk.
    """

    parent_child_chunks: list[ParentChildChunk]
    parent_mode: Literal["full-doc", "paragraph"] = "paragraph"

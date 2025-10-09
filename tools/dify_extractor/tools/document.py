from typing import Optional

from dify_plugin.invocations.file import UploadFileResponse
from pydantic import BaseModel, Field


class ChildDocument(BaseModel):
    """Class for storing a piece of text and associated metadata."""

    page_content: str

    vector: Optional[list[float]] = None

    """Arbitrary metadata about the page content (e.g., source, relationships to other
        documents, etc.).
    """
    metadata: dict = Field(default_factory=dict)


class Document(BaseModel):
    """Class for storing a piece of text and associated metadata."""

    page_content: str

    vector: Optional[list[float]] = None

    """Arbitrary metadata about the page content (e.g., source, relationships to other
        documents, etc.).
    """
    metadata: dict = Field(default_factory=dict)

    provider: Optional[str] = "dify"

    children: Optional[list[ChildDocument]] = None

    def to_dict(self) -> dict:
        return {
            "page_content": self.page_content,
            "vector": self.vector if self.vector is not None else None,
            "metadata": self.metadata,
            "provider": self.provider,
            "children": [child.model_dump() for child in self.children]
            if self.children
            else None,
        }


class ExtractorResult(BaseModel):
    """Class for storing the result of an extractor."""

    md_content: str
    documents: Optional[list[Document]] = None
    img_list: Optional[list[UploadFileResponse]] = None
    origin_result: Optional[dict] = None

"""Abstract interface for document loader implementations."""

from abc import ABC, abstractmethod

from tools.context import ExtractionContext
from tools.document import ExtractorResult


class BaseExtractor(ABC):
    """Uniform interface for extracting a file from an extraction context."""

    def __init__(self, context: ExtractionContext) -> None:
        self.context = context

    @abstractmethod
    def extract(self) -> ExtractorResult:
        raise NotImplementedError

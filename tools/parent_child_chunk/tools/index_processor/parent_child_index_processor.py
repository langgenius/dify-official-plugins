"""Paragraph index processor."""

import uuid
from hashlib import sha256
from tools.cleaner.clean_processor import CleanProcessor
from tools.document import ChildDocument, Document
from tools.entities.entities import (
    ParentMode,
    Rule,
    ParentChildStructureChunk,
    ParentChildChunk,
)
from tools.splitter.fixed_text_splitter import FixedRecursiveCharacterTextSplitter


class ParentChildIndexProcessor:
    def transform(self, input_text: str, rules: Rule) -> ParentChildStructureChunk:
        if rules.parent_mode == ParentMode.PARAGRAPH:
            return self._process_paragraph_mode(input_text, rules)
        elif rules.parent_mode == ParentMode.FULL_DOC:
            return self._process_full_doc_mode(input_text, rules)
        else:
            raise ValueError(f"Unsupported parent mode: {rules.parent_mode}")

    def _process_paragraph_mode(
        self, input_text: str, rules: Rule
    ) -> ParentChildStructureChunk:
        all_documents = ParentChildStructureChunk(parent_child_chunks=[])
        splitter = FixedRecursiveCharacterTextSplitter.from_encoder(
            chunk_size=rules.segmentation.max_tokens,
            chunk_overlap=rules.segmentation.chunk_overlap,
            fixed_separator=rules.segmentation.separator,
            separators=["\n\n", "。", ". ", " ", ""],
        )
        # Clean text content
        input_text = self._clean_content(input_text, rules)
        # Split text into nodes
        text_nodes = splitter.split_text(text=input_text)
        for text_node in text_nodes:
            if text_node.strip():
                # Split text into child nodes
                child_nodes = self._split_child_nodes(text_node, rules)
                all_documents.parent_child_chunks.append(
                    ParentChildChunk(
                        parent_content=text_node,
                        child_contents=child_nodes,
                        parent_mode="paragraph",
                    )
                )
        return all_documents

    def _process_full_doc_mode(
        self, input_text: str, rules: Rule
    ) -> ParentChildStructureChunk:
        # Split document into child nodes
        child_nodes = self._split_child_nodes(input_text, rules)
        input_text = self._clean_page_content(input_text)
        parent_child_chunk = ParentChildChunk(
            parent_content=input_text, child_contents=child_nodes, parent_mode="full-doc"
        )
        return ParentChildStructureChunk(
            parent_child_chunks=[parent_child_chunk], parent_mode="full-doc"
        )

    def _split_child_nodes(self, input_text: str, rules: Rule) -> list[ChildDocument]:
        """Split a document node into child nodes."""
        if not rules.subchunk_segmentation:
            raise ValueError("No subchunk segmentation found in rules.")
        child_splitter = FixedRecursiveCharacterTextSplitter.from_encoder(
            chunk_size=rules.subchunk_segmentation.max_tokens,
            chunk_overlap=rules.subchunk_segmentation.chunk_overlap,
            fixed_separator=rules.subchunk_segmentation.separator,
            separators=["\n\n", "。", ". ", " ", ""],
        )
        child_nodes = []
        child_texts = child_splitter.split_text(input_text)
        for child_text in child_texts:
            if child_text.strip():
                child_text = self._clean_page_content(child_text)
                if child_text:
                    child_nodes.append(child_text)
        return child_nodes

    def _clean_content(self, content: str, rules: Rule) -> str:
        """Clean the content of a document."""
        return CleanProcessor.clean(content, rules=rules)

    def _clean_page_content(self, page_content: str) -> str:
        """Clean the page content by removing unwanted characters."""
        if page_content.startswith(".") or page_content.startswith("。"):
            page_content = page_content[1:].strip()
        return page_content


def generate_text_hash(text: str) -> str:
    """Generate a SHA-256 hash for the given text."""
    hash_text = str(text) + "None"
    return sha256(hash_text.encode()).hexdigest()

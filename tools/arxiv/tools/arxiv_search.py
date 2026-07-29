import logging
from typing import Any, Optional

import arxiv
from pydantic import BaseModel, Field

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from collections.abc import Generator

logger = logging.getLogger(__name__)


class ArxivAPIWrapper(BaseModel):
    """Wrapper around ArxivAPI.

    To use, you should have the ``arxiv`` python package installed.
    https://lukasschwab.me/arxiv.py/index.html
    This wrapper will use the Arxiv API to conduct searches and
    fetch document summaries. By default, it will return the document summaries
    of the top-k results.
    It limits the Document content by doc_content_chars_max.
    Set doc_content_chars_max=None if you don't want to limit the content size.

    Args:
        top_k_results: number of the top-scored document used for the arxiv tool
        ARXIV_MAX_QUERY_LENGTH: the cut limit on the query used for the arxiv tool.
        load_max_docs: a limit to the number of loaded documents
        load_all_available_meta:
            if True: the `metadata` of the loaded Documents contains all available
            meta info (see https://lukasschwab.me/arxiv.py/index.html#Result),
            if False: the `metadata` contains only the published date, title,
            authors and summary.
        doc_content_chars_max: an optional cut limit for the length of a document's
            content

    Example:
        .. code-block:: python

            arxiv = ArxivAPIWrapper(
                top_k_results = 3,
                ARXIV_MAX_QUERY_LENGTH = 300,
                load_max_docs = 3,
                load_all_available_meta = False,
                doc_content_chars_max = 40000
            )
            arxiv.run("tree of thought llm)
    """

    arxiv_search: type[arxiv.Search] = arxiv.Search  #: :meta private:
    arxiv_http_error: tuple[type[Exception]] = (
        arxiv.ArxivError,
        arxiv.UnexpectedEmptyPageError,
        arxiv.HTTPError,
    )
    top_k_results: int = 3
    ARXIV_MAX_QUERY_LENGTH: int = 300
    load_max_docs: int = 100
    load_all_available_meta: bool = False
    doc_content_chars_max: Optional[int] = 4000

    def run(self, query: str) -> str:
        """
        Performs an arxiv search and A single string
        with the publish date, title, authors, and summary
        for each article separated by two newlines.

        If an error occurs or no documents found, error text
        is returned instead. Wrapper for
        https://lukasschwab.me/arxiv.py/index.html#Search

        Args:
            query: a plaintext search query
        """
        try:
            search = self.arxiv_search(  # type: ignore
                query[: self.ARXIV_MAX_QUERY_LENGTH], max_results=self.top_k_results
            )
            results = arxiv.Client().results(search)
        except self.arxiv_http_error as ex:
            return f"Arxiv exception: {ex}"
        docs = [
            f"Published: {result.updated.date()}\n"
            f"Title: {result.title}\n"
            f"Authors: {', '.join(a.name for a in result.authors)}\n"
            f"Summary: {result.summary}"
            for result in results
        ]
        if docs:
            return "\n\n".join(docs)[: self.doc_content_chars_max]
        else:
            return "No good Arxiv Result was found"


class ArxivSearchInput(BaseModel):
    query: str = Field(..., description="Search query.")


class ArxivSearchTool(Tool):
    """
    A tool for searching articles on Arxiv.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invokes the Arxiv search tool with the given user ID and tool parameters.

        Args:
            tool_parameters (dict[str, Any]): The parameters for the tool, including the 'query' parameter.

        Returns:
            Generator[ToolInvokeMessage, None, None]: The result of the tool invocation,
             which can be a single message or a list of messages.
        """
        query = tool_parameters.get("query", "")

        if not query:
            yield self.create_text_message("Please input query")
            return

        arxiv = ArxivAPIWrapper()

        response = arxiv.run(query)

        yield self.create_text_message(self.session.model.summary.invoke(response, ""))

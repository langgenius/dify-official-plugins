import json
from contextlib import suppress
from pathlib import Path
from typing import Any, Set, List
from urllib.parse import urlparse

from pydantic import BaseModel, Field

PROJECT_PATH = Path(__file__).parent

KNOWLEDGE_CARD_SNIPPET = """
Description: {description}
Details:
{details}
"""

TOOL_INVOKE_TPL = """
Here are the search results in XML format:

```xml
<search_results>
{context}
</search_results>
```
"""

TOOL_INVOKE_SEGMENT_TPL = """
<search_result index="{i}">
  <title>{title}</title>
  <url>{url}</url>
  <date>{date}</date>
  <source>{source}</source>
  <snippet>
    {snippet}
  </snippet>
</search_result>
"""

# Standard search result types
STANDARD_RESULT_TYPES = ["news_results", "organic_results", "related_questions"]

# Knowledge graph ignored fields
KNOWLEDGE_GRAPH_IGNORE_FIELDS = {
    "title",
    "description",
    "knowledge_graph_search_link",
    "serpapi_knowledge_graph_search_link",
    "image",
    "Kgmid",
    "Entity_Type",
}


class SearchRef(BaseModel):
    title: str | None = ""
    url: str | None = ""
    content: str | None = ""
    site_name: str | None = ""
    date: str | None = ""

    def model_post_init(self, context: Any, /) -> None:
        with suppress(Exception):
            if not self.site_name and self.url:
                u = urlparse(self.url)
                self.site_name = u.netloc


class InstantSearchResponse(BaseModel):
    refs: List[SearchRef] = Field(default_factory=list)
    webpage_context: str = ""
    total: int = 0

    def model_post_init(self, context: Any, /) -> None:
        self.total = len(self.refs)
        self.webpage_context = self.to_webpage_context()

    def to_webpage_context(self) -> str:
        if not self.refs:
            return ""

        webpage_segments = [
            TOOL_INVOKE_SEGMENT_TPL.format(
                i=i + 1,
                title=ref.title,
                url=ref.url,
                date=ref.date,
                source=ref.site_name,
                snippet=ref.content,
            ).strip()
            for i, ref in enumerate(self.refs)
        ]
        search_results_xml = TOOL_INVOKE_TPL.format(context="\n".join(webpage_segments))
        return search_results_xml

    def to_dify_json_message(self) -> dict:
        if not self.refs:
            return {"search_results": [], "description": "No search results found"}
        return {"search_results": [ref.model_dump(mode="json") for ref in self.refs]}

    def to_dify_text_message(self) -> str:
        return self.webpage_context


def load_valid_countries(filepath: Path) -> set | None:
    """
    Load valid country codes from google-countries.json
    :param filepath:
    :return:
    """
    with suppress(Exception):
        if countries := json.loads(filepath.read_text(encoding="utf8")):
            return {country["country_code"] for country in countries}
    return None


def load_valid_languages(filepath: Path) -> set | None:
    """
    Load valid language codes from google-languages.json
    :param filepath:
    :return:
    """
    with suppress(Exception):
        if languages := json.loads(filepath.read_text(encoding="utf8")):
            return {language["language_code"] for language in languages}
    return None


def _is_valid_knowledge_field(key: str, value: Any) -> bool:
    """Check if a knowledge graph field is valid."""
    if not isinstance(value, str) or not isinstance(key, str):
        return False
    if key in KNOWLEDGE_GRAPH_IGNORE_FIELDS:
        return False
    if key.lower().endswith(("_link", "_stick")):
        return False
    return True


def to_refs(response: dict) -> List[SearchRef]:
    refs = []

    # 解析标准结果
    for result_type in STANDARD_RESULT_TYPES:
        results = response.get(result_type, [])
        for result in results:
            if not (snippet := result.get("snippet", "")):
                continue

            # 优化问答类型的片段
            if result_type == "related_questions":
                question = result.get("question", "")
                if question and snippet:
                    snippet = f"Ask:{question} --> Answer:{snippet}"

            refs.append(
                SearchRef(
                    url=result.get("link", ""),
                    title=result.get("title", ""),
                    content=snippet,
                    site_name=result.get("source", ""),
                    date=result.get("date", ""),
                )
            )

    # 解析知识图谱
    if knowledge_graph := response.get("knowledge_graph", {}):
        details = []
        for key, value in knowledge_graph.items():
            if not _is_valid_knowledge_field(key, value):
                continue
            details.append(f"- {key.title()}: {value}")

        snippet = KNOWLEDGE_CARD_SNIPPET.format(
            description=knowledge_graph.get("description", "").strip(), details="\n".join(details)
        ).strip()

        link_candidates = [
            "knowledge_graph_search_link",
            "serpapi_knowledge_graph_search_link",
            "website",
        ]

        link = ""
        for candidate in link_candidates:
            link = knowledge_graph.get(candidate, "")
            if link:
                break

        refs.append(
            SearchRef(
                title=knowledge_graph.get("title", ""),
                url=link,
                content=snippet,
                site_name=knowledge_graph.get("source", {}).get("name", ""),
            )
        )

    return refs


VALID_COUNTRIES: Set[str] | None = load_valid_countries(
    PROJECT_PATH.joinpath("google-countries.json")
)
VALID_LANGUAGES: Set[str] | None = load_valid_languages(
    PROJECT_PATH.joinpath("google-languages.json")
)

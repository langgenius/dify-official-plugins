from typing import Any, Generator

from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

import os

from tools import ddgs_hardening
from tools.ddgs_utils import SearchUnavailable, candidate_engines, search_with_retry

# A search that ends without results returns a plain-language report as the node's text output
# instead of failing the node (DDG_FAIL_SOFT=0 restores the failure). The engines' responses are
# not a fault in the tool, and a failed node stops the whole workflow run.
FAIL_SOFT = os.environ.get("DDG_FAIL_SOFT", "1").strip().lower() not in ("0", "false", "no", "off", "")


class DuckDuckGoSearchTool(Tool):
    """
    Tool for performing a search using DuckDuckGo search engine.
    """

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        query = tool_parameters.get("query")
        max_results = tool_parameters.get("max_results", 5)
        require_summary = tool_parameters.get("require_summary", False)
        proxy = tool_parameters.get("proxy_server", None)
        backend = tool_parameters.get("backend", None)
        response: list[dict[str, Any]] = []
        try:
            response = search_with_retry(
                "text", query, proxy=proxy, backend=backend, max_results=max_results
            )
        except SearchUnavailable as ex:
            if not FAIL_SOFT:
                raise
            yield self.create_text_message(text=ex.user_text)
        else:
            if require_summary:
                results = "\n".join([res.get("body") for res in response])
                results = self.summary_results(content=results, query=query)
                yield self.create_text_message(text=results)
            for res in response:
                yield self.create_json_message(res)
        yield from self._report(query, backend, len(response))

    def _report(self, query: str, backend: str | None, results_received: int) -> Generator[ToolInvokeMessage, None, None]:
        """Last JSON row and named output variables: what each engine did and the search's outcome.

        The row carries no ``url``/``href`` key, so code that flattens result rows skips it. A
        workflow routes on ``search_status`` (successful / no_result / blocked) or inspects
        ``engine_status`` per engine (successful / no_result / blocked / not_applied).
        """
        rows = ddgs_hardening.diagnostics_for(query)
        statuses = ddgs_hardening.engine_status(rows, candidate_engines("text", backend))
        outcome = ddgs_hardening.search_status(statuses)
        report = {
            "search_status": outcome,
            "engine_status": statuses,
            "results_received": results_received,
            "query": query,
        }
        yield self.create_json_message(report)
        if hasattr(self, "create_variable_message"):
            yield self.create_variable_message("search_status", outcome)
            yield self.create_variable_message("engine_status", statuses)

    def summary_results(self, content: str, query: str) -> str:
        summary = self.session.model.summary.invoke(
            text=content,
            instruction=query,
        )
        return summary

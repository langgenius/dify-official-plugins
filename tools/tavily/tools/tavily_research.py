import time
from typing import Any, Generator
from tavily import TavilyClient
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class TavilyResearch:
    """
    A class for conducting deep research using the Tavily Research API.

    Args:
        api_key (str): The API key for accessing the Tavily Research API.
        project_id (str, optional): The project ID for tracking and analytics.

    Methods:
        research: Creates a research task.
        get_research: Gets research results by request_id.
    """

    def __init__(self, api_key: str, project_id: str | None = None) -> None:
        self.client = TavilyClient(api_key=api_key, project_id=project_id)

    def research(self, params: dict[str, Any]) -> dict:
        """
        Creates a research task.

        Args:
            params (Dict[str, Any]): The research parameters, which may include:
                - input: Required. The research task or question to investigate.
                - model: Optional string. The model to use ('mini', 'pro', or 'auto').
                - citation_format: Optional string. Citation format ('numbered', 'mla', 'apa', 'chicago').

        Returns:
            dict: Response containing request_id, created_at, status, input, and model.
        """
        processed_params = self._process_params(params)
        return self.client.research(**processed_params)

    def get_research(self, request_id: str) -> dict:
        """
        Gets research results by request_id.

        Args:
            request_id: The research request ID.

        Returns:
            dict: Research response containing request_id, created_at, completed_at, status, content, and sources.
        """
        return self.client.get_research(request_id)

    def _process_params(self, params: dict[str, Any]) -> dict:
        """
        Processes and validates the research parameters.

        Args:
            params (Dict[str, Any]): The research parameters.

        Returns:
            dict: The processed parameters.
        """
        processed_params = {}

        # Required parameter: input
        if "input" in params and params["input"]:
            processed_params["input"] = params["input"].strip()
        else:
            raise ValueError("The 'input' parameter is required.")

        # Optional parameter: model
        if "model" in params and params["model"]:
            model = params["model"]
            if model not in ["mini", "pro", "auto"]:
                raise ValueError("model must be 'mini', 'pro', or 'auto'")
            processed_params["model"] = model

        # Optional parameter: citation_format
        if "citation_format" in params and params["citation_format"]:
            citation_format = params["citation_format"]
            if citation_format not in ["numbered", "mla", "apa", "chicago"]:
                raise ValueError("citation_format must be 'numbered', 'mla', 'apa', or 'chicago'")
            processed_params["citation_format"] = citation_format

        return processed_params


class TavilyResearchTool(Tool):
    """
    A tool for conducting deep research using Tavily Research.

    This tool creates a research task and polls for results until completion.
    It provides comprehensive research reports with citations.
    """

    # Polling configuration
    DEFAULT_POLL_INTERVAL_SECONDS = 3
    MAX_POLL_INTERVAL_SECONDS = 10

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invokes the Tavily Research tool with the given tool parameters.

        Args:
            tool_parameters (Dict[str, Any]): The parameters for the Tavily Research tool.
                - input: Required. The research task or question to investigate.
                - model: Optional. The model to use ('mini', 'pro', or 'auto').
                - citation_format: Optional. Citation format ('numbered', 'mla', 'apa', 'chicago').

        Yields:
            ToolInvokeMessage: The result of the Tavily Research tool invocation.
        """
        api_key = self.runtime.credentials.get("tavily_api_key")
        if not api_key:
            yield self.create_text_message(
                "Tavily API key is missing. Please set it in the credentials."
            )
            return

        research_input = tool_parameters.get("input", "")
        if not research_input:
            yield self.create_text_message("Please input a research question or task.")
            return

        project_id = tool_parameters.get("project_id")
        tavily_research = TavilyResearch(api_key, project_id=project_id)

        try:
            # Step 1: Create research task
            yield self.create_text_message("Starting research task...")

            create_response = tavily_research.research(tool_parameters)
            request_id = create_response.get("request_id")

            if not request_id:
                yield self.create_text_message(
                    "Failed to create research task: No request_id returned."
                )
                return

            yield self.create_text_message(
                f"Research task created (ID: {request_id}). Waiting for results..."
            )

            # Step 2: Poll for results
            start_time = time.time()
            poll_interval = self.DEFAULT_POLL_INTERVAL_SECONDS
            last_status = None

            while True:
                elapsed = time.time() - start_time

                # Poll for status
                try:
                    result = tavily_research.get_research(request_id)
                except Exception as e:
                    yield self.create_text_message(f"Error polling research status: {str(e)}")
                    return

                status = result.get("status", "unknown")

                # Report status change
                if status != last_status:
                    yield self.create_text_message(
                        f"Status: {status} (elapsed: {int(elapsed)}s)"
                    )
                    last_status = status

                # Check completion states
                if status == "completed":
                    break
                elif status == "failed":
                    error_msg = result.get("error", "Unknown error")
                    yield self.create_text_message(f"Research task failed: {error_msg}")
                    yield self.create_json_message(result)
                    return
                elif status in ["pending", "in_progress"]:
                    # Continue polling with exponential backoff (capped)
                    time.sleep(poll_interval)
                    poll_interval = min(poll_interval * 1.2, self.MAX_POLL_INTERVAL_SECONDS)
                else:
                    # Unknown status, keep polling but warn
                    yield self.create_text_message(f"Unknown status: {status}, continuing...")
                    time.sleep(poll_interval)

            # Step 3: Process completed results
            yield self.create_json_message(result)

            # Format text output
            text_output = self._format_results_as_text(result)
            yield self.create_text_message(text=text_output)

        except Exception as e:
            yield self.create_text_message(
                f"Error occurred during research: {str(e)}"
            )
            return

    def _format_results_as_text(self, result: dict) -> str:
        """
        Formats the research results into markdown text.

        Args:
            result (dict): The research result.

        Returns:
            str: The formatted markdown text.
        """
        output_lines = []

        # Header
        output_lines.append("# Research Report\n")

        # Metadata
        if result.get("request_id"):
            output_lines.append(f"**Request ID:** {result['request_id']}")
        if result.get("created_at"):
            output_lines.append(f"**Created:** {result['created_at']}")
        if result.get("completed_at"):
            output_lines.append(f"**Completed:** {result['completed_at']}")
        if result.get("response_time"):
            output_lines.append(f"**Response Time:** {result['response_time']:.2f}s")

        output_lines.append("")  # Empty line

        # Content
        content = result.get("content", "")
        if content:
            output_lines.append("## Research Findings\n")
            output_lines.append(content)
            output_lines.append("")

        # Sources
        sources = result.get("sources", [])
        if sources:
            output_lines.append("## Sources\n")
            for idx, source in enumerate(sources, 1):
                if isinstance(source, dict):
                    title = source.get("title", "Untitled")
                    url = source.get("url", "")
                    output_lines.append(f"{idx}. [{title}]({url})")
                else:
                    output_lines.append(f"{idx}. {source}")

        return "\n".join(output_lines)

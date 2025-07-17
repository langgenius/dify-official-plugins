import logging
from dataclasses import dataclass
from typing import Any, Optional, List, Dict
from collections.abc import Generator
from openai import OpenAI
from yarl import URL
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


# ---------------------------------------------------------------------------
# Dataclass helpers for cleaner typing & structured data representation
# ---------------------------------------------------------------------------


@dataclass
class ToolCallDetail:
    tool: str
    action: str
    query: Optional[str] = None
    url: Optional[str] = None
    pattern: Optional[str] = None
    summary_text: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict excluding None values."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class ResponseData:
    response_id: Optional[str]
    status: Optional[str]
    model: Optional[str]
    background: Optional[bool] = None
    max_tool_calls: Optional[int] = None
    tools: Optional[List[str]] = None
    error: Optional[str] = None
    research_process: Optional[List[Dict[str, Any]]] = None
    usage: Optional[Dict[str, int]] = None
    reasoning_effort: Optional[str] = None
    summary: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Return a dict representation excluding any None values."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


class DeepResearchTool(Tool):
    """
    Tool to perform deep research using OpenAI's specialized models.
    """

    def _get_openai_client(self, tool_parameters: dict) -> OpenAI:
        """Initializes and returns an OpenAI client."""
        openai_organization = self.runtime.credentials.get("openai_organization_id")
        openai_base_url = self.runtime.credentials.get("openai_base_url")
        timeout = tool_parameters.get("timeout")

        return OpenAI(
            api_key=self.runtime.credentials["openai_api_key"],
            base_url=str(URL(openai_base_url) / "v1") if openai_base_url else None,
            organization=openai_organization,
            timeout=timeout if timeout is not None else 3600,
        )

    def _create_response_json(self, response: Any) -> Dict[str, Any]:
        """Builds a structured JSON dict from an OpenAI response using dataclasses."""

        # Base response fields
        resp_data = ResponseData(
            response_id=getattr(response, "id", None),
            status=getattr(response, "status", None),
            model=getattr(response, "model", None),
            background=getattr(response, "background", None),
            max_tool_calls=getattr(response, "max_tool_calls", None),
            tools=[tool.type for tool in getattr(response, "tools", [])] or None,
            error=getattr(response, "error", None),
            # Extract reasoning details if present
            reasoning_effort=(
                (getattr(response, "reasoning", None) or {}).get("effort")
                if isinstance(getattr(response, "reasoning", None), dict)
                else getattr(getattr(response, "reasoning", None), "effort", None)
            ),
            summary=(
                (getattr(response, "reasoning", None) or {}).get("summary")
                if isinstance(getattr(response, "reasoning", None), dict)
                else getattr(getattr(response, "reasoning", None), "summary", None)
            ),
        )

        # Research process (if any tool calls present)
        if getattr(response, "output", None):
            calls: List[ToolCallDetail] = []
            for item in response.output:
                if item.type == "web_search_call":
                    act = item.action
                    calls.append(
                        ToolCallDetail(
                            tool="web_search",
                            action=act.type,
                            query=getattr(act, "query", None),
                            url=getattr(act, "url", None),
                            pattern=getattr(act, "pattern", None),
                        )
                    )
                elif item.type == "code_interpreter_call":
                    calls.append(
                        ToolCallDetail(tool="code_interpreter", action="execute_code")
                    )
                elif item.type == "reasoning":
                    # Each reasoning item may contain multiple summary entries. Capture them all.
                    for summ in getattr(item, "summary", []) or []:
                        # Only include textual summaries for now.
                        if getattr(summ, "type", None) == "summary_text":
                            calls.append(
                                ToolCallDetail(
                                    tool="reasoning",
                                    action="summary_text",
                                    summary_text=getattr(summ, "text", None),
                                )
                            )
            if calls:
                resp_data.research_process = [c.to_dict() for c in calls]

        # Usage stats
        if getattr(response, "usage", None):
            resp_data.usage = {
                "total_tokens": response.usage.total_tokens,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

        return resp_data.to_dict()

    def _build_tools(
        self, use_web_search: bool, use_code_interpreter: bool
    ) -> list[dict[str, Any]]:
        """Returns the tools list expected by the OpenAI SDK based on flags."""
        tools: list[dict[str, Any]] = []
        if use_web_search:
            tools.append({"type": "web_search_preview"})
        if use_code_interpreter:
            tools.append({"type": "code_interpreter", "container": {"type": "auto"}})
        return tools

    def _invoke(
        self, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invoke the deep research tool.
        """
        # --- Initialize OpenAI Client ---
        client = self._get_openai_client(tool_parameters)

        # --- Parameter Extraction and Validation ---
        action = tool_parameters.get("action", "start")
        handler_map = {
            "start": self._handle_start,
            "cancel": self._handle_cancel,
            "retrieve": self._handle_retrieve,
        }
        handler = handler_map.get(action)
        if handler is None:
            yield self.create_text_message("Error: Invalid action specified.")
        else:
            yield from handler(client, tool_parameters)

    def _handle_start(
        self, client: OpenAI, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Handles the 'start' action."""
        prompt = tool_parameters.get("prompt")
        if not prompt or not isinstance(prompt, str):
            yield self.create_text_message(
                "Error: Research Prompt is required for 'start' action."
            )
            return

        model = tool_parameters.get("model", "o3-deep-research")
        use_web_search = tool_parameters.get("use_web_search", True)
        use_code_interpreter = tool_parameters.get("use_code_interpreter", True)
        max_tool_calls = tool_parameters.get("max_tool_calls")
        temperature = tool_parameters.get("temperature")
        reasoning_effort_param = tool_parameters.get("reasoning_effort")
        summary_param = tool_parameters.get("summary")

        if not use_web_search and not use_code_interpreter:
            yield self.create_text_message(
                "Error: At least one data source (web search or code interpreter) must be enabled."
            )
            return

        tools = self._build_tools(use_web_search, use_code_interpreter)

        create_args: dict[str, Any] = {
            "model": model,
            "input": prompt,
            "tools": tools,
            "background": True,  # Always run in the background for the 'start' action
        }

        # Optional advanced parameters (reasoning dict encapsulates effort & summary)
        reasoning_cfg: Dict[str, Any] = {}
        if reasoning_effort_param is not None:
            reasoning_cfg["effort"] = reasoning_effort_param
        if summary_param is not None:
            reasoning_cfg["summary"] = summary_param
        if reasoning_cfg:
            create_args["reasoning"] = reasoning_cfg

        # Include temperature if provided (allow explicit 0 value); default will be handled by API
        if temperature is not None:
            try:
                create_args["temperature"] = float(temperature)
            except (ValueError, TypeError):
                yield self.create_text_message(
                    "Error: Temperature must be a number between 0 and 2."
                )
                return

        if max_tool_calls is not None:
            try:
                create_args["max_tool_calls"] = int(max_tool_calls)
            except (ValueError, TypeError):
                yield self.create_text_message(
                    "Error: Max Tool Calls must be a valid number."
                )
                return

        try:
            response = client.responses.create(**create_args)
            logging.info(f"Start action raw response: {response}")
            yield self.create_text_message(
                f"Successfully started deep research task. Response ID: {response.id}"
            )

            # Return structured JSON data for the start action
            json_data = self._create_response_json(response)
            yield self.create_json_message(json_data)
        except Exception as e:
            logging.error(f"Failed to start deep research task: {e}", exc_info=True)
            yield self.create_text_message(f"Failed to start deep research task: {e}")

    def _handle_cancel(
        self, client: OpenAI, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Handles the 'cancel' action."""
        response_id = tool_parameters.get("response_id")
        if not response_id:
            yield self.create_text_message(
                "Error: Response ID is required for 'cancel' action."
            )
            return

        try:
            cancelled_response = client.responses.cancel(response_id)
            logging.info(f"Cancel action raw response: {cancelled_response}")
            if cancelled_response.status == "cancelled":
                yield self.create_text_message(
                    f"Successfully cancelled research task with ID: {response_id}"
                )
            else:
                yield self.create_text_message(
                    f"Could not cancel task {response_id}. Current status: {cancelled_response.status}"
                )

            # Return structured JSON data for the cancel action
            json_data = self._create_response_json(cancelled_response)
            yield self.create_json_message(json_data)
        except Exception as e:
            logging.error(
                f"Failed to cancel research task {response_id}: {e}", exc_info=True
            )
            yield self.create_text_message(
                f"Failed to cancel research task {response_id}: {e}"
            )

    def _handle_retrieve(
        self, client: OpenAI, tool_parameters: dict
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Handles the 'retrieve' action."""
        response_id = tool_parameters.get("response_id")
        if not response_id:
            yield self.create_text_message(
                "Error: Response ID is required for 'retrieve' action."
            )
            return

        try:
            response = client.responses.retrieve(response_id)
            logging.info(f"Retrieve action raw response: {response}")

            if response.status == "completed":
                logging.info(
                    f"Completed response: {self._format_output_with_numbered_citations(response)}"
                )
                yield from self._process_completed_response(response)
            elif response.status == "failed":
                yield from self._process_failed_response(response)
            else:
                yield self.create_text_message(
                    f"Status for task `{response_id}`: {response.status}"
                )

                # For other non-terminal statuses (e.g. queued), return the full context
                json_data = self._create_response_json(response)
                yield self.create_json_message(json_data)

        except Exception as e:
            logging.error(
                f"Failed to retrieve research task {response_id}: {e}", exc_info=True
            )
            yield self.create_text_message(
                f"Failed to retrieve research task {response_id}: {e}"
            )

    def _process_failed_response(
        self, response
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Processes a failed response object, yielding clear error messages."""
        error_details = getattr(response, "error", None)
        error_message = "An unknown error occurred."
        error_code = "unknown_error"

        if error_details:
            # The error object can be a dict or an object, so we use getattr.
            error_message = getattr(error_details, "message", str(error_details))
            error_code = getattr(error_details, "code", "unknown_error")

        yield self.create_text_message(
            f"Status for task `{response.id}`: {response.status}"
        )
        yield self.create_text_message(
            f"Error: Deep research task failed (Code: {error_code})."
        )
        yield self.create_text_message(f"Reason: {error_message}")

        # Return a simplified, structured JSON error response
        error_json = {
            "response_id": response.id,
            "status": response.status,
            "error": {
                "code": error_code,
                "message": error_message,
            },
        }
        yield self.create_json_message(error_json)

    def _process_completed_response(
        self, response
    ) -> Generator[ToolInvokeMessage, None, None]:
        """Processes a completed response object."""
        # Format and yield the final report as a text message
        formatted_report = self._format_output_with_numbered_citations(response)
        if formatted_report:
            yield self.create_text_message(formatted_report)

        structured_data = self._create_response_json(response)

        # Yield structured data as a JSON message
        yield self.create_json_message(structured_data)

    def _format_output_with_numbered_citations(self, response) -> str:
        """Formats output text with inline numbered citations and a reference list.
        The implementation walks the annotations once, builds a mapping of URL → number,
        then streams the final string together, avoiding expensive string slicing and
        double-passes over the data.
        """

        # Find the first (and usually only) output_text chunk in the response
        message_content = next(
            (
                content_part
                for item in response.output
                if item.type == "message" and hasattr(item, "content")
                for content_part in item.content
                if content_part.type == "output_text"
            ),
            None,
        )

        if message_content is None:
            return ""

        text: str = message_content.text
        annotations = getattr(message_content, "annotations", None) or []

        if not annotations:
            return text  # No citations to process

        # Preserve first-appearance order when numbering URLs
        url_to_num: Dict[str, int] = {}
        url_to_title: Dict[str, str] = {}
        for ann in annotations:
            url = getattr(ann, "url", None)
            if url and url not in url_to_num:
                idx = len(url_to_num) + 1
                url_to_num[url] = idx
                raw_title = getattr(ann, "title", None)
                if raw_title and isinstance(raw_title, str):
                    title: str = raw_title
                else:
                    try:
                        # Use hostname from the URL; if missing, fallback to placeholder
                        title = URL(url).host or "Unknown Source"
                    except Exception:
                        title = "Unknown Source"

                url_to_title[url] = title

        # Build the body with inline citations in a single pass
        parts: List[str] = []
        cursor = 0
        for ann in sorted(annotations, key=lambda a: a.start_index):
            url = getattr(ann, "url", None)
            if not url or url not in url_to_num:
                continue

            num = url_to_num[url]
            parts.append(text[cursor : ann.start_index])
            parts.append(f" [[{num}]]({url})")
            cursor = ann.end_index
        parts.append(text[cursor:])

        result = "".join(parts)

        # Append reference section
        if url_to_num:
            result += "\n\n---\n## References\n"
            # Sort by citation number for a clean, ordered list
            for url, num in sorted(url_to_num.items(), key=lambda item: item[1]):
                title = url_to_title[url]
                result += f"{num}. [{title}]({url})\n"

        return result

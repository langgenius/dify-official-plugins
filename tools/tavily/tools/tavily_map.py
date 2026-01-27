from typing import Any, Generator
from tavily import TavilyClient
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool


class TavilyMap:
    """
    A class for mapping website structure using the Tavily Map API.

    Args:
        api_key (str): The API key for accessing the Tavily Map API.

    Methods:
        map: Retrieves a list of URLs from a website starting from a root URL.
    """

    def __init__(self, api_key: str) -> None:
        self.client = TavilyClient(api_key=api_key)

    def map(self, params: dict[str, Any]) -> dict:
        """
        Maps a website structure starting from a root URL.

        Args:
            params (Dict[str, Any]): The mapping parameters, which may include:
                - url: Required. The root URL to begin the mapping.
                - instructions: Optional string. Natural language guidance for crawling.
                - max_depth: Optional integer. Exploration distance from base URL (1-5).
                - max_breadth: Optional integer. Links followed per page level (1-500).
                - limit: Optional integer. Total links processed before halting.
                - select_paths: Optional list. Regex patterns to select specific paths.
                - select_domains: Optional list. Regex patterns to filter domains.
                - exclude_paths: Optional list. Regex patterns to exclude paths.
                - exclude_domains: Optional list. Regex patterns to exclude domains.
                - allow_external: Optional boolean. Include external domain links.
                - timeout: Optional float. Maximum wait duration (10-150 seconds).
                - include_usage: Optional boolean. Return credit consumption data.

        Returns:
            dict: The mapping results containing discovered URLs.
        """
        processed_params = self._process_params(params)

        return self.client.map(**processed_params)

    def _process_params(self, params: dict[str, Any]) -> dict:
        """
        Processes and validates the mapping parameters.

        Args:
            params (Dict[str, Any]): The mapping parameters.

        Returns:
            dict: The processed parameters.
        """
        processed_params = {}

        # Required parameter: url
        if "url" in params and params["url"]:
            processed_params["url"] = params["url"].strip()
        else:
            raise ValueError("The 'url' parameter is required.")

        # Optional string parameter: instructions
        if "instructions" in params and params["instructions"]:
            processed_params["instructions"] = params["instructions"]

        # Optional integer parameters with bounds
        if "max_depth" in params and params["max_depth"] is not None:
            max_depth = params["max_depth"]
            if isinstance(max_depth, str):
                max_depth = int(max_depth)
            if max_depth < 1 or max_depth > 5:
                raise ValueError("max_depth must be between 1 and 5")
            processed_params["max_depth"] = max_depth

        if "max_breadth" in params and params["max_breadth"] is not None:
            max_breadth = params["max_breadth"]
            if isinstance(max_breadth, str):
                max_breadth = int(max_breadth)
            if max_breadth < 1 or max_breadth > 500:
                raise ValueError("max_breadth must be between 1 and 500")
            processed_params["max_breadth"] = max_breadth

        if "limit" in params and params["limit"] is not None:
            limit = params["limit"]
            if isinstance(limit, str):
                limit = int(limit)
            if limit < 1:
                raise ValueError("limit must be at least 1")
            processed_params["limit"] = limit

        # Optional list parameters (comma-separated strings or lists)
        for key in ["select_paths", "select_domains", "exclude_paths", "exclude_domains"]:
            if key in params and params[key]:
                value = params[key]
                if isinstance(value, str):
                    # Split by comma and strip whitespace
                    processed_params[key] = [
                        item.strip() for item in value.split(",") if item.strip()
                    ]
                elif isinstance(value, list):
                    processed_params[key] = value

        # Optional boolean parameter: allow_external
        if "allow_external" in params and params["allow_external"] is not None:
            value = params["allow_external"]
            if isinstance(value, str):
                processed_params["allow_external"] = value.lower() == "true"
            else:
                processed_params["allow_external"] = bool(value)

        # Optional float parameter: timeout
        if "timeout" in params and params["timeout"] is not None:
            timeout = params["timeout"]
            if isinstance(timeout, str):
                timeout = float(timeout)
            if timeout < 10 or timeout > 150:
                raise ValueError("timeout must be between 10 and 150 seconds")
            processed_params["timeout"] = timeout

        # Optional boolean parameter: include_usage
        if "include_usage" in params and params["include_usage"] is not None:
            value = params["include_usage"]
            if isinstance(value, str):
                processed_params["include_usage"] = value.lower() == "true"
            else:
                processed_params["include_usage"] = bool(value)

        return processed_params


class TavilyMapTool(Tool):
    """
    A tool for mapping website structure using Tavily Map.

    This tool discovers and returns a list of URLs from a website starting from
    a root URL, with options to control crawl depth, breadth, and filtering.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invokes the Tavily Map tool with the given tool parameters.

        Args:
            tool_parameters (Dict[str, Any]): The parameters for the Tavily Map tool.
                - url: Required. The root URL to begin the mapping.
                - instructions: Optional. Natural language guidance for crawling.
                - max_depth: Optional. Exploration distance from base URL (1-5).
                - max_breadth: Optional. Links followed per page level (1-500).
                - limit: Optional. Total links processed before halting.
                - select_paths: Optional. Comma-separated regex patterns to select paths.
                - select_domains: Optional. Comma-separated regex patterns to filter domains.
                - exclude_paths: Optional. Comma-separated regex patterns to exclude paths.
                - exclude_domains: Optional. Comma-separated regex patterns to exclude domains.
                - allow_external: Optional. Include external domain links.
                - timeout: Optional. Maximum wait duration (10-150 seconds).
                - include_usage: Optional. Return credit consumption data.

        Yields:
            ToolInvokeMessage: The result of the Tavily Map tool invocation.
        """
        api_key = self.runtime.credentials.get("tavily_api_key")
        if not api_key:
            yield self.create_text_message(
                "Tavily API key is missing. Please set it in the credentials."
            )
            return

        url = tool_parameters.get("url", "")
        if not url:
            yield self.create_text_message("Please input a URL to map.")
            return

        tavily_map = TavilyMap(api_key)

        try:
            map_results = tavily_map.map(tool_parameters)
        except Exception as e:
            yield self.create_text_message(
                f"Error occurred while mapping website: {str(e)}"
            )
            return

        if not map_results.get("results"):
            yield self.create_text_message(
                f"No URLs could be discovered from '{url}'."
            )
        else:
            # Return JSON result
            yield self.create_json_message(map_results)

            # Return text message with formatted results
            text_message_content = self._format_results_as_text(
                map_results, tool_parameters
            )
            yield self.create_text_message(text=text_message_content)

    def _format_results_as_text(
        self, map_results: dict, tool_parameters: dict[str, Any]
    ) -> str:
        """
        Formats the mapping results into a markdown text.

        Args:
            map_results (dict): The mapping results.
            tool_parameters (dict): The tool parameters selected by the user.

        Returns:
            str: The formatted markdown text.
        """
        output_lines = []

        base_url = map_results.get("base_url", tool_parameters.get("url", ""))
        output_lines.append(f"# Website Map for: {base_url}\n")

        results = map_results.get("results", [])
        output_lines.append(f"**Total URLs discovered:** {len(results)}\n")

        if map_results.get("response_time"):
            output_lines.append(
                f"**Response time:** {map_results['response_time']:.2f} seconds\n"
            )

        if map_results.get("usage"):
            usage = map_results["usage"]
            output_lines.append(f"**API Credits used:** {usage}\n")

        output_lines.append("\n## Discovered URLs:\n")

        for idx, url in enumerate(results, 1):
            output_lines.append(f"{idx}. {url}\n")

        return "\n".join(output_lines)

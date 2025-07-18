from typing import Any, Generator
from tavily import TavilyClient
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from .utils import process_images, process_favicons


class TavilySearch:
    """
    A class for performing search operations using the Tavily Search API.

    Args:
        api_key (str): The API key for accessing the Tavily Search API.

    Methods:
        search: Retrieves search results from the Tavily Search API.
    """

    def __init__(self, api_key: str) -> None:
        self.client = TavilyClient(api_key=api_key)

    def search(self, params: dict[str, Any]) -> dict:
        """
        Retrieves search results from the Tavily Search API.

        Args:
            params (Dict[str, Any]): The search parameters.

        Returns:
            dict: The search results.

        """
        if "api_key" in params:
            del params["api_key"]

        processed_params = self._process_params(params)

        return self.client.search(**processed_params)

    def _process_params(self, params: dict[str, Any]) -> dict:
        """
        Processes and validates the search parameters.

        Args:
            params (Dict[str, Any]): The search parameters.

        Returns:
            dict: The processed parameters.
        """
        processed_params = {}
        for key, value in params.items():
            if value is None or value == "None" or value == "not_specified":
                continue
            if key in ["include_domains", "exclude_domains"]:
                if isinstance(value, str):
                    processed_params[key] = [
                        domain.strip() for domain in value.replace(",", " ").split()
                    ]
            elif key in [
                "include_images",
                "include_image_descriptions",
                "include_answer",
                "include_raw_content",
                "auto_parameters",
                "include_favicon",
            ]:
                if isinstance(value, str):
                    processed_params[key] = value.lower() == "true"
                else:
                    processed_params[key] = bool(value)
            elif key in ["max_results", "days", "chunks_per_source"]:
                if isinstance(value, str):
                    processed_params[key] = int(value)
                else:
                    processed_params[key] = value
            elif key in ["search_depth", "topic", "query", "time_range", "country"]:
                processed_params[key] = value
            else:
                pass
        processed_params.setdefault("search_depth", "basic")
        processed_params.setdefault("topic", "general")
        processed_params.setdefault("max_results", 5)
        if processed_params.get("topic") == "news":
            processed_params.setdefault("days", 7)
        if processed_params.get("search_depth") == "advanced":
            processed_params.setdefault("chunks_per_source", 3)
        return processed_params


class TavilySearchTool(Tool):
    """
    A tool for searching Tavily using a given query.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invokes the Tavily search tool with the given user ID and tool parameters.

        Args:
            user_id (str): The ID of the user invoking the tool.
            tool_parameters (Dict[str, Any]): The parameters for the Tavily search tool.

        Returns:
            ToolInvokeMessage | list[ToolInvokeMessage]: The result of the Tavily search tool invocation.
        """
        api_key = self.runtime.credentials.get("tavily_api_key")
        if not api_key:
            yield self.create_text_message(
                "Tavily API key is missing. Please set it in the credentials."
            )
            return

        query = tool_parameters.get("query", "")
        if not query:
            yield self.create_text_message("Please input a query.")
            return

        tavily_search = TavilySearch(api_key)
        try:
            search_results = tavily_search.search(tool_parameters)
        except Exception as e:
            yield self.create_text_message(f"Error occurred while searching: {str(e)}")
            return
        if not search_results.get("results"):
            yield self.create_text_message(f"No results found for '{query}' in Tavily.")
            return
        else:
            # Return JSON result
            yield self.create_json_message(search_results)

            # Return text message with formatted results
            text_message_content = self._format_results_as_text(
                search_results, tool_parameters
            )
            yield self.create_text_message(text=text_message_content)

            # Process images from search results if include_images is enabled
            if tool_parameters.get("include_images", False) and search_results.get(
                "images"
            ):
                image_urls = [
                    image.get("url") if isinstance(image, dict) else image
                    for image in search_results.get("images", [])
                ]
                yield from process_images(self, image_urls)

            # Process favicons from search results if include_favicon is enabled
            if tool_parameters.get("include_favicon", False) and search_results.get(
                "results"
            ):
                yield from process_favicons(self, search_results.get("results", []))

    def _format_results_as_text(
        self, search_results: dict, tool_parameters: dict[str, Any]
    ) -> str:
        """
        Formats the search results into a markdown text based on user-selected parameters.

        Args:
            search_results (dict): The search results.
            tool_parameters (dict): The tool parameters selected by the user.

        Returns:
            str: The formatted markdown text.
        """
        output_lines = []
        if tool_parameters.get("include_answer", False) and search_results.get(
            "answer"
        ):
            output_lines.append(f"**Answer:** {search_results['answer']}\n")

        if "results" in search_results:
            for idx, result in enumerate(search_results["results"], 1):
                title = result.get("title", "No Title")
                url = result.get("url", "")
                content = result.get("content", "")
                published_date = result.get("published_date", "")
                score = result.get("score", "")
                output_lines.append(f"# Result {idx}: [{title}]({url})\n")
                if tool_parameters.get("topic") == "news" and published_date:
                    output_lines.append(f"**Published Date:** {published_date}\n")
                output_lines.append(f"**URL:** {url}\n")
                if score:
                    output_lines.append(f"**Relevance Score:** {score}\n")

                # Add favicon to the result
                if tool_parameters.get("include_favicon", False) and result.get(
                    "favicon"
                ):
                    output_lines.append(
                        f"**Favicon:** ![Favicon for {result.get('title', 'website')}]({result['favicon']})\n"
                    )

                if content:
                    output_lines.append(f"**Content:**\n{content}\n")

                if tool_parameters.get("include_raw_content", False) and result.get(
                    "raw_content"
                ):
                    output_lines.append(f"**Raw Content:**\n{result['raw_content']}\n")
                output_lines.append("---\n")

        # Display all images if requested
        if tool_parameters.get("include_images", False) and search_results.get(
            "images"
        ):
            output_lines.append("**Images:**\n")
            for image in search_results["images"]:
                if isinstance(image, dict):
                    image_url = image.get("url")
                    description = image.get("description", "Tavily search result image")
                else:
                    image_url = image
                    description = "Tavily search result image"

                if image_url:
                    output_lines.append(f"![{description}]({image_url})\n")
            output_lines.append("\n")

        return "\n".join(output_lines)

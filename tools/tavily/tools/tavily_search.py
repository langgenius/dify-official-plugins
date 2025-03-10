from typing import Any, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

TAVILY_API_URL = "https://api.tavily.com"


class TavilySearch:
    """
    A class for performing search operations using the Tavily Search API.

    Args:
        api_key (str): The API key for accessing the Tavily Search API.

    Methods:
        raw_results: Retrieves raw search results from the Tavily Search API.
    """

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def raw_results(self, params: dict[str, Any]) -> dict:
        """
        Retrieves raw search results from the Tavily Search API.

        Args:
            params (Dict[str, Any]): The search parameters.

        Returns:
            dict: The raw search results.

        """
        if "api_key" in params:
            del params["api_key"]
            
        processed_params = self._process_params(params)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}"
        }
        
        response = requests.post(f"{TAVILY_API_URL}/search", json=processed_params, headers=headers)
        response.raise_for_status()
        return response.json()

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
            ]:
                if isinstance(value, str):
                    processed_params[key] = value.lower() == "true"
                else:
                    processed_params[key] = bool(value)
            elif key in ["max_results", "days"]:
                if isinstance(value, str):
                    processed_params[key] = int(value)
                else:
                    processed_params[key] = value
            elif key in ["search_depth", "topic", "query", "time_range"]:
                processed_params[key] = value
            else:
                pass
        processed_params.setdefault("search_depth", "basic")
        processed_params.setdefault("topic", "general")
        processed_params.setdefault("max_results", 5)
        if processed_params.get("topic") == "news":
            processed_params.setdefault("days", 3)
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
        query = tool_parameters.get("query", "")
        api_key = self.runtime.credentials.get("tavily_api_key")
        if not api_key:
            yield self.create_text_message(
                "Tavily API key is missing. Please set the 'tavily_api_key' in credentials."
            )
            return
        if not query:
            yield self.create_text_message("Please input a query.")
            return
        tavily_search = TavilySearch(api_key)
        try:
            raw_results = tavily_search.raw_results(tool_parameters)
        except requests.HTTPError as e:
            yield self.create_text_message(f"Error occurred while searching: {str(e)}")
            return
        if not raw_results.get("results"):
            yield self.create_text_message(f"No results found for '{query}' in Tavily.")
            return
        else:
            # Return JSON result
            yield self.create_json_message(raw_results)
            
            # Return text message with formatted results
            text_message_content = self._format_results_as_text(
                raw_results, tool_parameters
            )
            yield self.create_text_message(text=text_message_content)
            
            # Process images from search results if include_images is enabled
            if tool_parameters.get("include_images", False) and raw_results.get("images"):
                for image in raw_results["images"]:
                    image_url = image.get("url")
                    if image_url:
                        try:
                            # Download image content
                            image_response = requests.get(image_url, timeout=10)
                            image_response.raise_for_status()
                            
                            # Get mime type from response headers
                            content_type = image_response.headers.get('Content-Type', 'image/jpeg')
                            
                            # Extract filename from URL or generate one
                            filename = image_url.split('/')[-1]
                            if '?' in filename:
                                filename = filename.split('?')[0]
                            
                            # Use description as alt text if available
                            alt_text = image.get('description', 'Tavily search result image')
                            
                            # Return as blob message - this automatically adds to 'files' variable
                            yield self.create_blob_message(
                                blob=image_response.content,
                                meta={
                                    "mime_type": content_type,
                                    "filename": filename,
                                    "alt_text": alt_text
                                }
                            )
                        except Exception as e:
                            # Log error but continue with other images
                            print(f"Failed to download image {image_url}: {str(e)}")

    def _format_results_as_text(
        self, raw_results: dict, tool_parameters: dict[str, Any]
    ) -> str:
        """
        Formats the raw results into a markdown text based on user-selected parameters.

        Args:
            raw_results (dict): The raw search results.
            tool_parameters (dict): The tool parameters selected by the user.

        Returns:
            str: The formatted markdown text.
        """
        output_lines = []
        if tool_parameters.get("include_answer", False) and raw_results.get("answer"):
            output_lines.append(f"**Answer:** {raw_results['answer']}\n")
        if tool_parameters.get("include_images", False) and raw_results.get("images"):
            output_lines.append("**Images:**\n")
            for image in raw_results["images"]:
                if (
                    tool_parameters.get("include_image_descriptions", False)
                    and "description" in image
                ):
                    output_lines.append(f"![{image['description']}]({image['url']})\n")
                else:
                    output_lines.append(f"![]({image['url']})\n")
        if "results" in raw_results:
            for idx, result in enumerate(raw_results["results"], 1):
                title = result.get("title", "No Title")
                url = result.get("url", "")
                content = result.get("content", "")
                published_date = result.get("published_date", "")
                score = result.get("score", "")
                output_lines.append(f"### Result {idx}: [{title}]({url})\n")
                if tool_parameters.get("topic") == "news" and published_date:
                    output_lines.append(f"**Published Date:** {published_date}\n")
                output_lines.append(f"**URL:** {url}\n")
                if score:
                    output_lines.append(f"**Relevance Score:** {score}\n")
                if content:
                    output_lines.append(f"**Content:**\n{content}\n")
                if tool_parameters.get("include_raw_content", False) and result.get(
                    "raw_content"
                ):
                    output_lines.append(f"**Raw Content:**\n{result['raw_content']}\n")
                output_lines.append("---\n")
        return "\n".join(output_lines)

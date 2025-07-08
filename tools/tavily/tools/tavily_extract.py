from typing import Any, Generator
from tavily import TavilyClient
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from .utils import process_images, process_favicons


class TavilyExtract:
    """
    A class for extracting content from web pages using the Tavily Extract API.

    Args:
        api_key (str): The API key for accessing the Tavily Extract API.

    Methods:
        extract: Retrieves extracted content from the Tavily Extract API.
    """

    def __init__(self, api_key: str) -> None:
        self.client = TavilyClient(api_key=api_key)

    def extract(self, params: dict[str, Any]) -> dict:
        """
        Retrieves extracted content from the Tavily Extract API.

        Args:
            params (Dict[str, Any]): The extraction parameters, which may include:
                - urls: Required. A string or list of URLs to extract content from.
                - include_images: Optional boolean. Whether to include images in the response. Default is False.
                - include_favicon: Optional boolean. Whether to include favicon URLs. Default is False.
                - extract_depth: Optional string. The depth of extraction ('basic' or 'advanced'). Default is 'basic'.
                  Advanced extraction retrieves more data but costs more credits and may increase latency.
                - format: Optional string. The format of extracted content ('markdown' or 'text'). Default is 'markdown'.

        Returns:
            dict: The extracted content with results.
        """
        processed_params = self._process_params(params)

        return self.client.extract(**processed_params)

    def _process_params(self, params: dict[str, Any]) -> dict:
        """
        Processes and validates the extraction parameters.

        Args:
            params (Dict[str, Any]): The extraction parameters.

        Returns:
            dict: The processed parameters.
        """
        processed_params = {}

        if "urls" in params:
            urls = params["urls"]
            if isinstance(urls, str):
                url_list = [url.strip() for url in urls.split(",") if url.strip()]
                processed_params["urls"] = url_list
            elif isinstance(urls, list):
                processed_params["urls"] = urls
        else:
            raise ValueError("The 'urls' parameter is required.")

        if not processed_params.get("urls"):
            raise ValueError("At least one valid URL must be provided.")

        if "include_images" in params:
            processed_params["include_images"] = params["include_images"]

        if "include_favicon" in params:
            processed_params["include_favicon"] = params["include_favicon"]

        if "extract_depth" in params:
            extract_depth = params["extract_depth"]
            if extract_depth not in ["basic", "advanced"]:
                raise ValueError("extract_depth must be either 'basic' or 'advanced'")
            processed_params["extract_depth"] = extract_depth

        if "format" in params:
            format = params["format"]
            if format not in ["markdown", "text"]:
                raise ValueError("format must be either 'markdown' or 'text'")
            processed_params["format"] = format

        return processed_params


class TavilyExtractTool(Tool):
    """
    A tool for extracting content from web pages using Tavily Extract.

    This tool extracts raw content from specified URLs, with options to include images
    and control the depth of extraction. Advanced extraction retrieves more data but
    costs more credits and may increase latency.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invokes the Tavily Extract tool with the given tool parameters.

        Args:
            tool_parameters (Dict[str, Any]): The parameters for the Tavily Extract tool.
                - urls: Required. A comma-separated list of URLs to extract content from.
                - include_images: Optional. Whether to include images in the response.
                - extract_depth: Optional. The depth of extraction ('basic' or 'advanced').

        Yields:
            ToolInvokeMessage: The result of the Tavily Extract tool invocation.
        """
        api_key = self.runtime.credentials.get("tavily_api_key")
        if not api_key:
            yield self.create_text_message(
                "Tavily API key is missing. Please set it in the credentials."
            )
            return

        urls = tool_parameters.get("urls", "")
        if not urls:
            yield self.create_text_message("Please input at least one URL to extract.")
            return

        tavily_extract = TavilyExtract(api_key)

        try:
            extract_results = tavily_extract.extract(tool_parameters)
        except Exception as e:
            yield self.create_text_message(
                f"Error occurred while extracting content: {str(e)}"
            )
            return

        if not extract_results.get("results"):
            yield self.create_text_message(
                "No content could be extracted from the provided URLs."
            )
        else:
            # Return JSON result
            yield self.create_json_message(extract_results)

            # Return text message with formatted results
            text_message_content = self._format_results_as_text(extract_results)
            yield self.create_text_message(text=text_message_content)

            # Process images and favicons
            if extract_results.get("results"):
                results = extract_results["results"]
                if tool_parameters.get("include_images", False):
                    image_urls = []
                    for result in results:
                        if "images" in result and result.get("images"):
                            image_urls.extend(result["images"])
                    if image_urls:
                        yield from process_images(self, image_urls)
                if tool_parameters.get("include_favicon", False):
                    yield from process_favicons(self, results)

    def _format_results_as_text(self, extract_results: dict) -> str:
        """
        Formats the extraction results into a markdown text.

        Args:
            extract_results (dict): The extraction results.

        Returns:
            str: The formatted markdown text.
        """
        output_lines = []
        for idx, result in enumerate(extract_results.get("results", []), 1):
            url = result.get("url", "")
            raw_content = result.get("raw_content", "")
            output_lines.append(f"# Extracted Content {idx}: {url}\n")

            # Add favicon to the result
            if result.get("favicon"):
                output_lines.append(
                    f"**Favicon:** ![Favicon for {url}]({result['favicon']})\n"
                )

            output_lines.append(f"**Raw Content:**\n{raw_content}\n")

            # Add images to the result
            if "images" in result and result["images"]:
                output_lines.append("**Images:**\n")
                for image_url in result["images"]:
                    output_lines.append(f"![Image from {url}]({image_url})\n")

            output_lines.append("---\n")

        if extract_results.get("failed_results"):
            output_lines.append("# Failed URLs:\n")
            for failed in extract_results["failed_results"]:
                url = failed.get("url", "")
                error = failed.get("error", "Unknown error")
                output_lines.append(f"- {url}: {error}\n")

        return "\n".join(output_lines)

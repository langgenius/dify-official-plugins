from typing import Any, Generator
from tavily import TavilyClient
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool
from .utils import process_images, process_favicons


class TavilyCrawl:
    """
    A class for crawling websites using the Tavily Crawl API.

    Args:
        api_key (str): The API key for accessing the Tavily Crawl API.

    Methods:
        crawl: Crawls a website starting from the given URL.
    """

    def __init__(self, api_key: str) -> None:
        self.client = TavilyClient(api_key=api_key)

    def crawl(self, params: dict[str, Any]) -> dict:
        """
        Crawls a website starting from the given URL.

        Args:
            params (Dict[str, Any]): The crawl parameters, which may include:
                - url: Required. The base URL to start crawling from.
                - max_depth: Optional int. Maximum depth to crawl (how many links deep).
                - max_breadth: Optional int. Maximum breadth to crawl (links per page).
                - limit: Optional int. Maximum number of pages to crawl.
                - instructions: Optional string. Natural language instructions for the crawler.
                - chunks_per_source: Optional int. Max relevant chunks per source (1-5, only with instructions).
                - select_paths: Optional list. URL paths to include in the crawl.
                - select_domains: Optional list. Domains to include in the crawl.
                - exclude_paths: Optional list. URL paths to exclude from the crawl.
                - exclude_domains: Optional list. Domains to exclude from the crawl.
                - allow_external: Optional boolean. Whether to allow crawling external domains.
                - include_images: Optional boolean. Whether to include images in results.
                - categories: Optional list. Page categories to focus on.
                - extract_depth: Optional string. Extraction depth ('basic' or 'advanced').
                - format: Optional string. Content format ('markdown' or 'text').
                - timeout: Optional int. Request timeout in seconds (10-150).
                - include_favicon: Optional boolean. Whether to include favicon URLs.
                - include_usage: Optional boolean. Whether to include credit usage info.

        Returns:
            dict: The crawl results with pages and their content.
        """
        processed_params = self._process_params(params)
        return self.client.crawl(**processed_params)

    def _process_params(self, params: dict[str, Any]) -> dict:
        """
        Processes and validates the crawl parameters.

        Args:
            params (Dict[str, Any]): The crawl parameters.

        Returns:
            dict: The processed parameters.
        """
        processed_params = {}

        if "url" in params:
            processed_params["url"] = params["url"]
        else:
            raise ValueError("The 'url' parameter is required.")

        if "max_depth" in params and params["max_depth"] is not None:
            max_depth = params["max_depth"]
            if isinstance(max_depth, str):
                max_depth = int(max_depth)
            processed_params["max_depth"] = max_depth

        if "max_breadth" in params and params["max_breadth"] is not None:
            max_breadth = params["max_breadth"]
            if isinstance(max_breadth, str):
                max_breadth = int(max_breadth)
            processed_params["max_breadth"] = max_breadth

        if "limit" in params and params["limit"] is not None:
            limit = params["limit"]
            if isinstance(limit, str):
                limit = int(limit)
            processed_params["limit"] = limit

        if "instructions" in params and params["instructions"]:
            processed_params["instructions"] = params["instructions"]

        if "chunks_per_source" in params and params["chunks_per_source"] is not None:
            chunks_per_source = params["chunks_per_source"]
            if isinstance(chunks_per_source, str):
                chunks_per_source = int(chunks_per_source)
            processed_params["chunks_per_source"] = chunks_per_source

        # Process path/domain lists
        for key in ["select_paths", "select_domains", "exclude_paths", "exclude_domains"]:
            if key in params and params[key]:
                value = params[key]
                if isinstance(value, str):
                    processed_params[key] = [item.strip() for item in value.split(",") if item.strip()]
                elif isinstance(value, list):
                    processed_params[key] = value

        if "allow_external" in params and params["allow_external"] is not None:
            value = params["allow_external"]
            if isinstance(value, str):
                processed_params["allow_external"] = value.lower() == "true"
            else:
                processed_params["allow_external"] = bool(value)

        if "include_images" in params and params["include_images"] is not None:
            value = params["include_images"]
            if isinstance(value, str):
                processed_params["include_images"] = value.lower() == "true"
            else:
                processed_params["include_images"] = bool(value)

        if "include_favicon" in params and params["include_favicon"] is not None:
            value = params["include_favicon"]
            if isinstance(value, str):
                processed_params["include_favicon"] = value.lower() == "true"
            else:
                processed_params["include_favicon"] = bool(value)

        if "categories" in params and params["categories"]:
            value = params["categories"]
            if isinstance(value, str):
                processed_params["categories"] = [cat.strip() for cat in value.split(",") if cat.strip()]
            elif isinstance(value, list):
                processed_params["categories"] = value

        if "extract_depth" in params and params["extract_depth"]:
            extract_depth = params["extract_depth"]
            if extract_depth not in ["basic", "advanced"]:
                raise ValueError("extract_depth must be either 'basic' or 'advanced'")
            processed_params["extract_depth"] = extract_depth

        if "format" in params and params["format"]:
            format_value = params["format"]
            if format_value not in ["markdown", "text"]:
                raise ValueError("format must be either 'markdown' or 'text'")
            processed_params["format"] = format_value

        if "timeout" in params and params["timeout"] is not None:
            timeout = params["timeout"]
            if isinstance(timeout, str):
                timeout = int(timeout)
            processed_params["timeout"] = timeout

        if "include_usage" in params and params["include_usage"] is not None:
            value = params["include_usage"]
            if isinstance(value, str):
                processed_params["include_usage"] = value.lower() == "true"
            else:
                processed_params["include_usage"] = bool(value)

        return processed_params


class TavilyCrawlTool(Tool):
    """
    A tool for crawling websites using Tavily Crawl.

    This tool crawls a website starting from a base URL, following links to discover
    and extract content from multiple pages. It supports filtering by paths, domains,
    and categories, with configurable depth and breadth limits.
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        Invokes the Tavily Crawl tool with the given tool parameters.

        Args:
            tool_parameters (Dict[str, Any]): The parameters for the Tavily Crawl tool.
                - url: Required. The base URL to start crawling from.
                - max_depth: Optional. Maximum depth to crawl (1-5).
                - max_breadth: Optional. Maximum breadth to crawl.
                - limit: Optional. Maximum number of pages to crawl.
                - instructions: Optional. Natural language instructions for the crawler.
                - chunks_per_source: Optional. Max chunks per source (1-5, only with instructions).
                - select_paths: Optional. URL paths to include (comma-separated).
                - select_domains: Optional. Domains to include (comma-separated).
                - exclude_paths: Optional. URL paths to exclude (comma-separated).
                - exclude_domains: Optional. Domains to exclude (comma-separated).
                - allow_external: Optional. Whether to allow external domains (default: true).
                - include_images: Optional. Whether to include images.
                - categories: Optional. Page categories to focus on.
                - extract_depth: Optional. Extraction depth ('basic' or 'advanced').
                - format: Optional. Content format ('markdown' or 'text').
                - timeout: Optional. Request timeout in seconds (10-150, default: 150).
                - include_favicon: Optional. Whether to include favicons.
                - include_usage: Optional. Whether to include credit usage info.

        Yields:
            ToolInvokeMessage: The result of the Tavily Crawl tool invocation.
        """
        api_key = self.runtime.credentials.get("tavily_api_key")
        if not api_key:
            yield self.create_text_message(
                "Tavily API key is missing. Please set it in the credentials."
            )
            return

        url = tool_parameters.get("url", "")
        if not url:
            yield self.create_text_message("Please input a URL to crawl.")
            return

        tavily_crawl = TavilyCrawl(api_key)

        try:
            crawl_results = tavily_crawl.crawl(tool_parameters)
        except Exception as e:
            yield self.create_text_message(
                f"Error occurred while crawling: {str(e)}"
            )
            return

        if not crawl_results.get("results"):
            yield self.create_text_message(
                f"No pages could be crawled from '{url}'."
            )
        else:
            # Return JSON result
            yield self.create_json_message(crawl_results)

            # Return text message with formatted results
            text_message_content = self._format_results_as_text(crawl_results)
            yield self.create_text_message(text=text_message_content)

            # Process images and favicons
            if crawl_results.get("results"):
                results = crawl_results["results"]
                if tool_parameters.get("include_images", False):
                    image_urls = []
                    for result in results:
                        if "images" in result and result.get("images"):
                            image_urls.extend(result["images"])
                    if image_urls:
                        yield from process_images(self, image_urls)
                if tool_parameters.get("include_favicon", False):
                    yield from process_favicons(self, results)

    def _format_results_as_text(self, crawl_results: dict) -> str:
        """
        Formats the crawl results into a markdown text.

        Args:
            crawl_results (dict): The crawl results.

        Returns:
            str: The formatted markdown text.
        """
        output_lines = []

        # Add base URL info if available
        if crawl_results.get("base_url"):
            output_lines.append(f"**Base URL:** {crawl_results['base_url']}\n")

        # Add total pages crawled
        results = crawl_results.get("results", [])
        output_lines.append(f"**Pages Crawled:** {len(results)}\n")
        output_lines.append("---\n")

        for idx, result in enumerate(results, 1):
            url = result.get("url", "")
            title = result.get("title", "No Title")
            raw_content = result.get("raw_content", "")

            output_lines.append(f"# Page {idx}: {title}\n")
            output_lines.append(f"**URL:** {url}\n")

            # Add favicon to the result
            if result.get("favicon"):
                output_lines.append(
                    f"**Favicon:** ![Favicon for {title}]({result['favicon']})\n"
                )

            if raw_content:
                # Truncate very long content for display
                display_content = raw_content[:2000] + "..." if len(raw_content) > 2000 else raw_content
                output_lines.append(f"**Content:**\n{display_content}\n")

            # Add images to the result
            if "images" in result and result["images"]:
                output_lines.append("**Images:**\n")
                for image_url in result["images"][:5]:  # Limit to first 5 images per page
                    output_lines.append(f"![Image from {title}]({image_url})\n")

            output_lines.append("---\n")

        if crawl_results.get("failed_results"):
            output_lines.append("# Failed URLs:\n")
            for failed in crawl_results["failed_results"]:
                url = failed.get("url", "")
                error = failed.get("error", "Unknown error")
                output_lines.append(f"- {url}: {error}\n")

        return "\n".join(output_lines)

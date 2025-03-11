from typing import Any, Generator
import requests
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

TAVILY_API_URL = "https://api.tavily.com"


class TavilyExtract:
    """
    A class for extracting content from web pages using the Tavily Extract API.

    Args:
        api_key (str): The API key for accessing the Tavily Extract API.

    Methods:
        extract_content: Retrieves extracted content from the Tavily Extract API.
    """

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def extract_content(self, params: dict[str, Any]) -> dict:
        """
        Retrieves extracted content from the Tavily Extract API.

        Args:
            params (Dict[str, Any]): The extraction parameters, which may include:
                - urls: Required. A string or list of URLs to extract content from.
                - include_images: Optional boolean. Whether to include images in the response. Default is False.
                - extract_depth: Optional string. The depth of extraction ('basic' or 'advanced'). Default is 'basic'.
                  Advanced extraction retrieves more data but costs more credits and may increase latency.

        Returns:
            dict: The extracted content with results.
        """
        processed_params = self._process_params(params)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        response = requests.post(
            f"{TAVILY_API_URL}/extract", 
            json=processed_params,
            headers=headers
        )
        response.raise_for_status()
        return response.json()

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
                url_list = [url.strip() for url in urls.split(',') if url.strip()]
                processed_params["urls"] = url_list
            elif isinstance(urls, list):
                processed_params["urls"] = urls
        else:
            raise ValueError("The 'urls' parameter is required.")
        
        if not processed_params.get("urls"):
            raise ValueError("At least one valid URL must be provided.")
        
        if "include_images" in params:
            processed_params["include_images"] = params["include_images"]
            
        if "extract_depth" in params:
            extract_depth = params["extract_depth"]
            if extract_depth not in ["basic", "advanced"]:
                raise ValueError("extract_depth must be either 'basic' or 'advanced'")
            processed_params["extract_depth"] = extract_depth
            
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
        urls = tool_parameters.get("urls", "")
        api_key = self.runtime.credentials.get("tavily_api_key")
        
        if not api_key:
            yield self.create_text_message(
                "Tavily API key is missing. Please set the 'tavily_api_key' in credentials."
            )
            return
            
        if not urls:
            yield self.create_text_message("Please input at least one URL to extract.")
            return
            
        tavily_extract = TavilyExtract(api_key)
        
        try:
            raw_results = tavily_extract.extract_content(tool_parameters)
        except requests.HTTPError as e:
            yield self.create_text_message(
                f"Error occurred while extracting content: {str(e)}"
            )
            return
            
        if not raw_results.get("results"):
            yield self.create_text_message(
                "No content could be extracted from the provided URLs."
            )
        else:
            # Return JSON result
            yield self.create_json_message(raw_results)
            
            # Return text message with formatted results
            text_message_content = self._format_results_as_text(raw_results)
            yield self.create_text_message(text=text_message_content)
            
            # Process images and return as file blobs
            # This will automatically add them to the 'files' variable
            for result in raw_results.get("results", []):
                if "images" in result and result["images"]:
                    for image_url in result["images"]:
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
                            
                            # Return as blob message - this automatically adds to 'files' variable
                            yield self.create_blob_message(
                                blob=image_response.content,
                                meta={
                                    "mime_type": content_type,
                                    "filename": filename
                                }
                            )
                        except Exception as e:
                            # Log error but continue with other images
                            print(f"Failed to download image {image_url}: {str(e)}")

    def _format_results_as_text(self, raw_results: dict) -> str:
        """
        Formats the raw extraction results into a markdown text.

        Args:
            raw_results (dict): The raw extraction results.

        Returns:
            str: The formatted markdown text.
        """
        output_lines = []
        for idx, result in enumerate(raw_results.get("results", []), 1):
            url = result.get("url", "")
            raw_content = result.get("raw_content", "")
            output_lines.append(f"## Extracted Content {idx}: {url}\n")
            output_lines.append(f"**Raw Content:**\n{raw_content}\n")
            
            if "images" in result and result["images"]:
                output_lines.append("**Images:**\n")
                for i, image_url in enumerate(result["images"], 1):
                    output_lines.append(f"![Image {i} from {url}]({image_url})\n")
                    
            output_lines.append("---\n")
            
        if raw_results.get("failed_results"):
            output_lines.append("## Failed URLs:\n")
            for failed in raw_results["failed_results"]:
                url = failed.get("url", "")
                error = failed.get("error", "Unknown error")
                output_lines.append(f"- {url}: {error}\n")
 
        return "\n".join(output_lines)

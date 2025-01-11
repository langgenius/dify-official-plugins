from typing import Any, Generator, Optional
import requests
from bs4 import BeautifulSoup
from requests.exceptions import RequestException

class CosenseSearchError(Exception):
    """Base exception for Cosense search errors"""
    pass

class CosenseSearchTool:
    def __init__(self, connect_sid: Optional[str] = None):
        self.connect_sid = connect_sid
        self.base_url = "https://scrapbox.io"

    @classmethod
    def from_credentials(cls, credentials: dict[str, Any]) -> "CosenseSearchTool":
        return cls(
            connect_sid=credentials.get("connect_sid")
        )

    def invoke(self, tool_parameters: dict[str, Any]) -> Generator[dict[str, Any], None, None]:
        project_name = tool_parameters.get("project_name")
        query = tool_parameters.get("query")
        
        if not project_name:
            raise CosenseSearchError("Project name is required")
        if not query:
            raise CosenseSearchError("Search query is required")
        
        cookies = {}
        if self.connect_sid:
            cookies["connect.sid"] = self.connect_sid

        try:
            response = requests.get(
                f"{self.base_url}/{project_name}/search/page?q={query}",
                cookies=cookies,
                timeout=30
            )
            response.raise_for_status()
        except RequestException as e:
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 404:
                    raise CosenseSearchError(f"Project '{project_name}' not found") from e
                elif e.response.status_code == 403:
                    raise CosenseSearchError("Access denied. Private project requires valid connect.sid") from e
            raise CosenseSearchError(f"Failed to search Cosense: {str(e)}") from e

        soup = BeautifulSoup(response.text, 'html.parser')
        results = []
        
        for page in soup.select('.page-list-item'):
            title_elem = page.select_one('.title')
            desc_elem = page.select_one('.description')
            if not title_elem or not desc_elem:
                continue
            
            title = title_elem.text
            content = desc_elem.text
            url = f"{self.base_url}/{project_name}/{title}"
            
            results.append({
                "title": title,
                "content": content,
                "url": url
            })

        yield {
            "query": query,
            "project": project_name,
            "results": {
                "pages": results
            },
            "result_count": len(results)
        }

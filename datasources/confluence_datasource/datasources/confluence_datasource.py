from collections.abc import Generator
from typing import Any

import requests
from dify_plugin.entities.datasource import (
    DatasourceGetPagesResponse,
    DatasourceMessage,
    GetOnlineDocumentPageContentRequest,
    OnlineDocumentInfo,
    OnlineDocumentPage,
)
from dify_plugin.interfaces.datasource.online_document import OnlineDocumentDatasource
from bs4 import BeautifulSoup

class ConfluenceDataSource(OnlineDocumentDatasource):
    _BASE_URL = "https://your-domain.atlassian.net/wiki/rest/api"
    _API_VERSION = "v2"

    def _get_pages(self, datasource_parameters: dict[str, Any]) -> DatasourceGetPagesResponse:
        access_token = self.runtime.credentials.get("integration_secret")
        space_key = datasource_parameters.get("space_key")  
        if not access_token:
            raise ValueError("Access token not found in credentials")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        url = f"{self._BASE_URL}/content"
        params = {
            "type": "page",
            "expand": "space,version",
            "limit": 100,
        }
        if space_key:
            params["spaceKey"] = space_key

        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        pages = [
            OnlineDocumentPage(
                page_name=item.get("title", ""),
                page_id=item.get("id", ""),
                type=item.get("type", ""),
                last_edited_time=item.get("version", {}).get("createdAt"),
                parent_id=item.get("parentId", ""),
                page_icon=item.get("icon", {}),
            )
            for item in data.get("results", [])
        ]

        workspace_name = data["results"][0]["space"]["name"] if data["results"] else "Confluence"
        workspace_id = data["results"][0]["space"]["id"] if data["results"] else "unknown"
        workspace_icon = self.runtime.credentials.get("workspace_icon", "")

        online_document_info = OnlineDocumentInfo(
            workspace_name=workspace_name,
            workspace_icon=workspace_icon,
            workspace_id=workspace_id,
            pages=pages,
            total=len(pages),
        )
        return DatasourceGetPagesResponse(result=[online_document_info])

    def _get_content(self, page: GetOnlineDocumentPageContentRequest) -> Generator[DatasourceMessage, None, None]:
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token not found in credentials")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        page_id = page.page_id
        url = f"{self._BASE_URL}/content/{page_id}?expand=body.storage"

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            content_html = data["body"]["storage"]["value"]
            page_title = data["title"]
            workspace_id = page.workspace_id or "unknown"

            yield self.create_variable_message("content", self._html_to_text(content_html))
            yield self.create_variable_message("page_id", page_id)
            yield self.create_variable_message("workspace_id", workspace_id)
            yield self.create_variable_message("title", page_title)
        except Exception as e:
            raise ValueError(str(e)) from e
        
    
    def _html_to_text(self, html: str) -> str:
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "meta", "noscript"]):
            tag.decompose()

        text_parts = []
        for block in soup.find_all(["h1", "h2", "h3", "p", "li"]):
            text_parts.append(block.get_text(strip=True))

        return "\n".join(text_parts).strip()
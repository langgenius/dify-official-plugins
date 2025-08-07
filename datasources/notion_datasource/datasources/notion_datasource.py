from collections.abc import Generator
from typing import Any

import requests
from datasources.utils.notion_client import NotionClient
from datasources.utils.notion_extractor import NotionExtractor

from dify_plugin.entities.datasource import (
    DatasourceGetPagesResponse,
    DatasourceMessage,
    GetOnlineDocumentPageContentRequest,
    OnlineDocumentInfo,
)
from dify_plugin.interfaces.datasource.online_document import OnlineDocumentDatasource


class NotionDataSource(OnlineDocumentDatasource):
    _API_VERSION = "2022-06-28"
    _AUTH_URL = "https://api.notion.com/v1/oauth/authorize"
    _TOKEN_URL = "https://api.notion.com/v1/oauth/token"
    _NOTION_PAGE_SEARCH = "https://api.notion.com/v1/search"
    _NOTION_BLOCK_SEARCH = "https://api.notion.com/v1/blocks"
    _NOTION_BOT_USER = "https://api.notion.com/v1/users/me"

    def _get_pages(self, datasource_parameters: dict[str, Any]) -> DatasourceGetPagesResponse:
        # Get integration token from credentials
        access_token = self.runtime.credentials.get("integration_secret")
        if not access_token:
            raise ValueError("Access token not found in credentials")
        workspace_name = self.notion_workspace_info(access_token).get("workspace_name", "")
        workspace_icon = self.runtime.credentials.get("workspace_icon") or ""
        notion_client = NotionClient(access_token)
        pages = notion_client.get_authorized_pages()
        workspace_id = self.runtime.credentials.get("workspace_id") or ""
        online_document_info = OnlineDocumentInfo(
            workspace_name=workspace_name,
            workspace_icon=workspace_icon,
            workspace_id=workspace_id,
            pages=pages,
            total=len(pages),
        )
        return DatasourceGetPagesResponse(
            result=[online_document_info],
        )

    def _get_content(self, page: GetOnlineDocumentPageContentRequest) -> Generator[DatasourceMessage, None, None]:
        access_token = self.runtime.credentials.get("integration_secret")
        if not access_token:
            raise ValueError("Access token not found in credentials")
        try:
            notion_extractor = NotionExtractor(
                access_token=access_token,
                page_id=page.page_id,
                page_type=page.type,
                workspace_id=page.workspace_id,
            )
            online_document_res = notion_extractor.extract()
        except Exception as e:
            raise ValueError(str(e)) from e
        print(online_document_res)
        yield self.create_variable_message("content", online_document_res["content"])
        yield self.create_variable_message("page_id", online_document_res["page_id"])
        yield self.create_variable_message("workspace_id", online_document_res["workspace_id"])

    def notion_workspace_info(self, access_token: str):
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Notion-Version": self._API_VERSION,
        }
        response = requests.get(url=self._NOTION_BOT_USER, headers=headers, timeout=10)
        response_json = response.json()
        if "object" in response_json and response_json["object"] == "user":
            user_type = response_json["type"]
            user_info = response_json[user_type]
            return {
                "workspace_name": user_info.get("workspace_name", ""),
                "workspace_icon": user_info.get("workspace_icon", ""),
                "workspace_id": user_info.get("workspace_id", ""),
            }
        return {}

import logging
import re
import urllib.parse
from collections.abc import Generator
from typing import Any

import requests
from bs4 import BeautifulSoup
from dify_plugin.entities.datasource import (
    DatasourceGetPagesResponse,
    DatasourceMessage,
    GetOnlineDocumentPageContentRequest,
    OnlineDocumentInfo,
    OnlineDocumentPage,
)
from dify_plugin.interfaces.datasource.online_document import OnlineDocumentDatasource

logger = logging.getLogger(__name__)


class ConfluenceDataSource(OnlineDocumentDatasource):
    _API_BASE = "https://api.atlassian.com/ex/confluence"

    def _get_pages(self, datasource_parameters: dict[str, Any]) -> DatasourceGetPagesResponse:
        access_token = self.runtime.credentials.get("access_token")
        workspace_id = self.runtime.credentials.get("workspace_id")
        
        if not access_token:
            raise ValueError("Access token not found in credentials")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        # Use Confluence API v2 for better performance and cleaner structure
        url = f"{self._API_BASE}/{workspace_id}/wiki/api/v2/pages"
        params = {
            "limit": 100,  
            "sort": "-modified-date",
        }
        

        all_pages = []
        next_cursor = None
        
        # Handle pagination
        while True:
            if next_cursor:
                params["cursor"] = next_cursor
                
            try:
                response = requests.get(url, headers=headers, params=params, timeout=30)
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.HTTPError as e:
                if response.status_code == 401:
                    raise ValueError(
                        "Authentication failed (401 Unauthorized). The access token may have expired. "
                        "Please refresh the connection or reauthorize. If the problem persists, "
                        "the OAuth app may need reconfiguration."
                    ) from e
                else:
                    raise ValueError(f"Failed to fetch pages: {response.status_code} {response.text[:200]}") from e

            # Parse v2 response structure
            for item in data.get("results", []):
                # Extract relevant fields from v2 response
                page = OnlineDocumentPage(
                    page_name=item.get("title", ""),
                    page_id=item.get("id", ""),
                    type="page",  # v2 only returns pages in this endpoint
                    last_edited_time=item.get("version", {}).get("createdAt", ""),
                    parent_id=item.get("parentId", ""),
                    page_icon=None,  # v2 doesn't provide icon in list response
                )
                all_pages.append(page)
            
            # Check if there are more pages
            links = data.get("_links", {})
            if links.get("next"):
                # Extract cursor from next link
                next_url = links["next"]
                parsed = urllib.parse.urlparse(next_url)
                query_params = urllib.parse.parse_qs(parsed.query)
                next_cursor = query_params.get("cursor", [None])[0]
                if not next_cursor:
                    break
            else:
                break

        # Get workspace info from credentials
        workspace_name = self.runtime.credentials.get("workspace_name", "Confluence")
        workspace_id = self.runtime.credentials.get("workspace_id", "unknown")
        workspace_icon = self.runtime.credentials.get("workspace_icon", "")

        online_document_info = OnlineDocumentInfo(
            workspace_name=workspace_name,
            workspace_icon=workspace_icon,
            workspace_id=workspace_id,
            pages=all_pages,
            total=len(all_pages),
        )
        return DatasourceGetPagesResponse(result=[online_document_info])

    def _get_content(self, page: GetOnlineDocumentPageContentRequest) -> Generator[DatasourceMessage, None, None]:
        access_token = self.runtime.credentials.get("access_token")
        workspace_id = self.runtime.credentials.get("workspace_id")
        
        if not access_token:
            raise ValueError("Access token not found in credentials")
        if not workspace_id:
            raise ValueError("Workspace ID not found in credentials")

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        page_id = page.page_id
        # Use API v2 endpoint for getting page content
        url = f"{self._API_BASE}/{workspace_id}/wiki/api/v2/pages/{page_id}"
        
        # v2 allows specifying body format and other details
        params = {
            "body-format": "storage",  # Get the storage format (HTML)
        }

        try:
            logger.debug(f"Fetching page content from: {url}")
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            # v2 response structure is different
            page_title = data.get("title", "")
            page_status = data.get("status", "current")
            page_version = data.get("version", {}).get("number", 1)
            
            # Get the body content - v2 structure
            body = data.get("body", {})
            content_html = ""
            
            # v2 can have multiple body representations
            if "storage" in body:
                content_html = body["storage"].get("value", "")
            elif "atlas_doc_format" in body:
                # Handle Atlas Doc Format if present (newer format)
                content_html = body["atlas_doc_format"].get("value", "")
            else:
                logger.warning(f"No body content found for page {page_id}")
                content_html = "<p>No content available</p>"
                 
            # Convert HTML to text
            content_text = self._html_to_text(content_html)
            
            # Return content and metadata
            yield self.create_variable_message("content", content_text)
            yield self.create_variable_message("page_id", page_id)
            yield self.create_variable_message("workspace_id", page.workspace_id or workspace_id)
            yield self.create_variable_message("title", page_title)
            
        except requests.exceptions.HTTPError as e:
            if response.status_code == 404:
                logger.error(f"Page not found: {page_id}")
                raise ValueError(f"Page with ID '{page_id}' not found") from e
            elif response.status_code == 401:
                logger.error(f"Authentication failed for page: {page_id}")
                raise ValueError("Authentication failed. Please refresh or reauthorize the connection.") from e
            else:
                logger.error(f"Failed to fetch page content: {response.status_code}")
                raise ValueError(f"Failed to fetch page content: {response.status_code} {response.text[:200]}") from e
        except Exception as e:
            logger.error(f"Unexpected error fetching page content: {e}")
            raise ValueError(f"Error fetching page content: {str(e)}") from e
        
    
    def _html_to_text(self, html: str) -> str:
        """Convert Confluence HTML to plain text with improved formatting."""
        if not html:
            return ""
            
        soup = BeautifulSoup(html, "html.parser")

        # Remove unwanted tags
        for tag in soup(["script", "style", "meta", "noscript", "link"]):
            tag.decompose()

        # Handle Confluence-specific elements
        # Convert ac:structured-macro to readable format
        for macro in soup.find_all("ac:structured-macro"):
            macro_name = macro.get("ac:name", "")  # type: ignore
            if macro_name == "code":
                # Extract code content
                code_body = macro.find("ac:plain-text-body")  # type: ignore
                if code_body:
                    code_text = code_body.get_text()  # type: ignore
                    new_tag = soup.new_tag("p")
                    new_tag.string = f"\n```\n{code_text}\n```\n"
                    macro.replace_with(new_tag)  # type: ignore
            elif macro_name == "info" or macro_name == "note":
                # Extract info/note content
                rich_body = macro.find("ac:rich-text-body")  # type: ignore
                if rich_body:
                    note_text = rich_body.get_text(strip=True)  # type: ignore
                    new_tag = soup.new_tag("p")
                    new_tag.string = f"\n[{str(macro_name).upper()}]: {note_text}\n"
                    macro.replace_with(new_tag)  # type: ignore
            else:
                macro.decompose()  # type: ignore

        # Handle tables
        for table in soup.find_all("table"):
            rows = []
            for tr in table.find_all("tr"):  # type: ignore
                cells = [td.get_text(strip=True) for td in tr.find_all(["td", "th"])]  # type: ignore
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                table_text = "\n".join(rows)
                new_tag = soup.new_tag("p")
                new_tag.string = f"\n{table_text}\n"
                table.replace_with(new_tag)  # type: ignore

        # Extract text with better formatting
        text_parts = []
        
        # Process different block elements with appropriate spacing
        for element in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "div", "blockquote", "pre"]):
            text = element.get_text(strip=True)  # type: ignore
            if text:
                # Add appropriate formatting based on tag
                element_name = element.name  # type: ignore
                if element_name and element_name.startswith("h"):
                    level = int(element_name[1])
                    text = f"\n{'#' * level} {text}\n"
                elif element_name == "li":
                    # Check if it's part of ordered or unordered list
                    parent = element.parent  # type: ignore
                    if parent and hasattr(parent, 'name') and parent.name == "ol":
                        text = f"  * {text}"
                    else:
                        text = f"  - {text}"
                elif element_name == "blockquote":
                    text = f"\n> {text}\n"
                elif element_name == "pre":
                    text = f"\n```\n{text}\n```\n"
                    
                text_parts.append(text)

        # Join and clean up excessive whitespace
        result = "\n".join(text_parts)
        # Remove multiple consecutive newlines
        result = re.sub(r'\n{3,}', '\n\n', result)
        
        return result.strip()
import time
from typing import Any, Generator

import requests
from dify_plugin.entities.datasource import WebSiteInfo, WebSiteInfoDetail
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.interfaces.datasource.website import WebsiteCrawlDatasource


class BrightdataProvider(WebsiteCrawlDatasource):

    def _get_website_crawl(
        self, datasource_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        try:
            api_token = self.runtime.credentials["api_token"]
        except KeyError:
            raise Exception("Bright Data API token is required.")

        url = datasource_parameters.get("url", "").strip()
        if not url:
            raise Exception("URL cannot be empty.")

        try:

            crawl_res = WebSiteInfo(web_info_list=[], status="", total=0, completed=0)
            crawl_res.status = "processing"
            yield self.create_crawl_message(crawl_res)

            format = datasource_parameters.get("format", "markdown")
            markdown_content = self._scrape_as_markdown(
                self.runtime.credentials.get("zone", "dify_plugin"),
                url,
                api_token,
                format,
            )
            crawl_res.status = "completed"
            crawl_res.web_info_list = [
                WebSiteInfoDetail(
                    title=url,  # Any Better Ways?
                    source_url=url,
                    description=markdown_content,
                    content=markdown_content,
                )
            ]
            crawl_res.total = 1
            crawl_res.completed = 1
            yield self.create_crawl_message(crawl_res)

        except Exception as e:
            raise Exception(f"Web scraping failed: {str(e)}")

    def _scrape_as_markdown(
        self, zone: str, url: str, api_token: str, format: str
    ) -> str:
        """Use exact same API call as Bright Data MCP server"""

        headers = {
            "user-agent": "dify-plugin/1.0.0",  # todo check
            "authorization": f"Bearer {api_token}",
            "content-type": "application/json",
        }

        # Use the same zone as MCP server (hardcoded default)
        payload = {
            "url": url,
            "zone": zone,
            "format": "raw",
            "data_format": format,
        }

        try:
            response = requests.post(
                "https://api.brightdata.com/request",
                json=payload,
                headers=headers,
                timeout=180,
            )

            if response.status_code != 200:
                raise Exception(
                    f"Bright Data API error {response.status_code}: {response.text}"
                )

            return response.text

        except requests.exceptions.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")

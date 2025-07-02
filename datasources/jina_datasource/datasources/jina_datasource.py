import time

import requests
from typing import Any, Generator

from dify_plugin.entities.datasource import WebSiteInfo, WebSiteInfoDetail
from dify_plugin.interfaces.datasource.website import WebsiteCrawlDatasource
from dify_plugin.entities.tool import ToolInvokeMessage


class JinaReaderDatasource(WebsiteCrawlDatasource):
    _jina_reader_endpoint = "https://r.jina.ai/"
    _api_key: str

    def _get_website_crawl(
        self, datasource_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        api_key = self.runtime.credentials.get("api_key", "")
        self._api_key = api_key
        try:
            crawl_res = WebSiteInfo(web_info_list=[], status="", total=0, completed=0)
            start_res = self._handle_new_job(datasource_parameters)
            crawl_res.status = "processing"
            yield self.create_crawl_message(crawl_res)

            while True:
                status_data = self._handle_existing_job(start_res["job_id"])
                crawl_res.total = status_data["total"] or 0
                crawl_res.completed = status_data["current"] or 0
                crawl_res.web_info_list = status_data["data"] or []

                if status_data["status"] == "completed":
                    crawl_res.status = "completed"
                    yield self.create_crawl_message(crawl_res)
                    break
                else:
                    crawl_res.status = "processing"
                    yield self.create_crawl_message(crawl_res)
                    time.sleep(5)

        except Exception as e:
            raise ValueError(f"An error occurred: {str(e)}")

    def _handle_new_job(self, datasource_parameters: dict[str, Any]):
        url = datasource_parameters.get("url")
        crawl_sub_pages = datasource_parameters.get("crawl_sub_pages", False)
        limit = datasource_parameters.get("limit", 1)
        if not crawl_sub_pages:
            limit = 1
        response = requests.post(
            "https://adaptivecrawl-kir3wx7b3a-uc.a.run.app",
            json={
                "url": url,
                "maxPages": limit,
                "useSitemap": datasource_parameters.get("use_sitemap", True),
            },
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        if response.json().get("code") != 200:
            raise ValueError("Failed to crawl")
        return {
            "status": "active",
            "job_id": response.json().get("data", {}).get("taskId"),
        }

    def _handle_existing_job(self, job_id: str):
        response = requests.post(
            "https://adaptivecrawlstatus-kir3wx7b3a-uc.a.run.app",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
            json={"taskId": job_id},
        )
        if response.json().get("code") != 200:
            raise ValueError("Failed to crawl")
        data = response.json().get("data", {})
        crawl_status_data = {
            "status": data.get("status", "active"),
            "job_id": job_id,
            "total": len(data.get("urls", [])),
            "current": len(data.get("processed", [])) + len(data.get("failed", [])),
            "data": [],
            "time_consuming": data.get("duration", 0) / 1000,
        }
        if crawl_status_data["status"] == "completed":
            response = requests.post(
                "https://adaptivecrawlstatus-kir3wx7b3a-uc.a.run.app",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._api_key}",
                },
                json={"taskId": job_id, "urls": list(data.get("processed", {}).keys())},
            )
            data = response.json().get("data", {})
            web_info_list = [
                WebSiteInfoDetail(
                    title=item.get("data", {}).get("title"),
                    source_url=item.get("data", {}).get("url"),
                    description=item.get("data", {}).get("description"),
                    content=item.get("data", {}).get("content"),
                )
                for item in data.get("processed", {}).values()
            ]
            crawl_status_data["data"] = web_info_list
        return crawl_status_data

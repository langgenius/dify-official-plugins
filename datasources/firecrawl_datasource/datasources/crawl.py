import time
from collections.abc import Generator
from typing import Any, Mapping

from dify_plugin.entities.datasource import (
    WebSiteInfo,
    WebSiteInfoDetail,
    WebsiteCrawlMessage,
)
from dify_plugin.interfaces.datasource.website import WebsiteCrawlDatasource
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from requests import HTTPError

from datasources.firecrawl_app import FirecrawlApp, get_array_params, get_json_params


class CrawlDatasource(WebsiteCrawlDatasource):
    def _get_website_crawl(
        self, datasource_parameters: Mapping[str, Any]
    ) -> Generator[WebsiteCrawlMessage, None, None]:
        """
        the api doc:
        https://docs.firecrawl.dev/api-reference/endpoint/crawl
        """
        source_url = datasource_parameters.get("url")
        if not source_url:
            raise ValueError("Url is required")

        if not self.runtime.credentials.get("firecrawl_api_key"):
            raise ToolProviderCredentialValidationError("api key is required")

        try:
            app = FirecrawlApp(
                api_key=self.runtime.credentials.get("firecrawl_api_key"),
                base_url=self.runtime.credentials.get("base_url")
                or "https://api.firecrawl.dev",
            )

            crawl_sub_pages = datasource_parameters.get("crawl_subpages", True)

            scrapeOptions = {
                "onlyMainContent": datasource_parameters.get("only_main_content", True)
            }
            scrapeOptions = {
                k: v for k, v in scrapeOptions.items() if v not in (None, "")
            }

            payload = {
                "excludePaths": get_array_params(datasource_parameters, "exclude_paths")
                if crawl_sub_pages
                else [],
                "includePaths": get_array_params(datasource_parameters, "include_paths")
                if crawl_sub_pages
                else [],
                "maxDepth": datasource_parameters.get("max_depth")
                if crawl_sub_pages
                else None,
                "limit": 1
                if not crawl_sub_pages
                else datasource_parameters.get("limit", 5),
                "scrapeOptions": scrapeOptions or None,
            }
            payload = {k: v for k, v in payload.items() if v not in (None, "")}

            crawl_res = WebSiteInfo(web_info_list=[], status="", total=0, completed=0)

            _crawl_result = app.crawl_url(
                url=datasource_parameters["url"], wait=False, **payload
            )
            job_id = _crawl_result["id"]
            crawl_res.status = "processing"
            print(crawl_res)
            yield self.create_crawl_message(crawl_res)

            while True:
                status = app.check_crawl_status(job_id=job_id)
                if status["status"] == "completed":
                    self._process_completed_job(app, status, crawl_res)
                    crawl_res.status = "completed"
                    crawl_res.total = status["total"] or 0
                    crawl_res.completed = status["completed"] or 0
                    yield self.create_crawl_message(crawl_res)
                    break
                elif status["status"] == "failed":
                    raise HTTPError(f"Job {crawl_res.job_id} failed: {status['error']}")
                else:
                    crawl_res.status = "processing"
                    crawl_res.total = status["total"] or 0
                    crawl_res.completed = status["completed"] or 0
                    yield self.create_crawl_message(crawl_res)
                    time.sleep(5)

        except Exception as e:
            raise ValueError(f"An error occurred: {str(e)}")

    @staticmethod
    def _process_completed_job(app: FirecrawlApp, status: dict, crawl_res: WebSiteInfo):
        _format_res = app.format_crawl_status_response(status["status"], status)

        crawl_res.web_info_list = [
            WebSiteInfoDetail(
                source_url=item["source_url"],
                content=item["content"] or "",
                title=item["title"] or "",
                description=item["description"] or "",
            )
            for item in _format_res["data"]
        ]

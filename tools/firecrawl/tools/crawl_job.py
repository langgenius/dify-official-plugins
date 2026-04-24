from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

from .firecrawl_appx import FirecrawlApp


class CrawlJobTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        app = FirecrawlApp(
            api_key=self.runtime.credentials.get("firecrawl_api_key"), base_url=self.runtime.credentials.get("base_url")
        )
        operation = tool_parameters.get("operation", "get")
        if operation == "get":
            result = app.check_crawl_status(job_id=tool_parameters["job_id"])
        elif operation == "cancel":
            result = app.cancel_crawl_job(job_id=tool_parameters["job_id"])
        else:
            raise ValueError(f"Invalid operation: {operation}")
        yield self.create_json_message(result)

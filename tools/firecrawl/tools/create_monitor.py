from typing import Any, Generator
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin import Tool

from .firecrawl_appx import FirecrawlApp, get_array_params, get_json_params


class CreateMonitorTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Create a Firecrawl monitor: a recurring scrape that diffs each result
        against the last snapshot. Docs: https://docs.firecrawl.dev/features/monitors
        """
        app = FirecrawlApp(
            api_key=self.runtime.credentials.get("firecrawl_api_key"), base_url=self.runtime.credentials.get("base_url")
        )

        # The simplest, well-supported target shape: scrape one or more URLs.
        urls = get_array_params(tool_parameters, "urls") or []
        scrape_options = get_json_params(tool_parameters, "scrapeOptions")
        targets = []
        for url in urls:
            target: dict[str, Any] = {"type": "scrape", "url": url}
            if scrape_options:
                target["scrapeOptions"] = scrape_options
            targets.append(target)

        # Schedule: prefer a natural-language schedule, fall back to cron.
        schedule: dict[str, Any] = {}
        schedule_text = tool_parameters.get("scheduleText")
        cron = tool_parameters.get("cron")
        timezone = tool_parameters.get("timezone")
        if schedule_text:
            schedule["text"] = schedule_text
        elif cron:
            schedule["cron"] = cron
        if timezone:
            schedule["timezone"] = timezone

        payload: dict[str, Any] = {
            "name": tool_parameters["name"],
            "targets": targets,
        }
        if schedule:
            payload["schedule"] = schedule

        goal = tool_parameters.get("goal")
        if goal:
            payload["goal"] = goal
            payload["judgeEnabled"] = tool_parameters.get("judgeEnabled", True)

        retention_days = tool_parameters.get("retentionDays")
        if retention_days:
            payload["retentionDays"] = retention_days

        email = tool_parameters.get("email")
        if email:
            payload["notification"] = {"email": email}

        webhook_url = tool_parameters.get("webhookUrl")
        if webhook_url:
            payload["webhook"] = {"url": webhook_url}

        result = app.create_monitor(**payload)
        yield self.create_json_message(result)

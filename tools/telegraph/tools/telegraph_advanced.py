from collections.abc import Generator
from typing import Any

from ytelegraph import TelegraphAPI

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class TelegraphAdvancedTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        if tool_parameters["a_telegraph_access_token"]:
            access_token = tool_parameters["a_telegraph_access_token"]
        else:
            access_token = self.runtime.credentials["telegraph_access_token"]
        try:
            ph = TelegraphAPI(access_token)
        except Exception as e:
            ph_ok = False
            ph_error = f"Error:\n\n---\n\n{str(e)}\n\nFailed to initialize the API, please check the access token."
        title = tool_parameters["p_title"]
        content = tool_parameters["p_content"]
        try:
            author_name = tool_parameters["a_author_name"]
        except KeyError:
            author_name = ""
        try:
            author_url = tool_parameters["a_author_url"]
        except KeyError:
            author_url = ""
        try:
            ph_link = ph.create_page_md(title=title, content=content, author_name=author_name, author_url=author_url)
            ph_ok = True
        except Exception as e:
            ph_ok = False
            ph_error = f"Error:\n\n---\n\n{str(e)}\n\nFailed to create page, please check the parameters."
        yield self.create_json_message({
            "ok": ph_ok,
            "link": ph_link if ph_ok else ph_error,
        })
        # yield self.create_link_message(ph_link)
        # yield self.create_text_message(ph_link)

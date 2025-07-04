from collections.abc import Generator
from typing import Any

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from src.supabase import *


class DifyPluginPdmTemplateTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, Any, Any]:

        plugin = SupabasePlugin(
            credentials=SupabaseCredentials(**self.runtime.credentials)
        )

        for res in plugin.create_a_row(**tool_parameters):
            if isinstance(res, str):
                yield self.create_text_message(res)
            elif isinstance(res, list):
                yield self.create_json_message(
                    {
                        "data": res,
                    }
                )
            elif isinstance(res, dict):
                yield self.create_json_message(res)
            else:
                yield self.create_text_message(str(res))

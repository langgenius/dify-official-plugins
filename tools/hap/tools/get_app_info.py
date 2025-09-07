from collections.abc import Generator
from typing import Any, Dict, Optional

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

from tools.hap_api_utils import HapRequest


class GetAppInfoTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        try:
            client = HapRequest(self.runtime.credentials)
            resp: Dict[str, Any] = client.get("/v3/app")
        except Exception as e:
            yield self.create_json_message({"success": False, "error_msg": f"Request failed: {e}"})
            return
        
        # Convert type numbers to strings
        if resp.get("success") and resp.get("data") and resp["data"].get("sections"):
            self._convert_type_to_string(resp["data"]["sections"])
        
        yield self.create_json_message(resp)
        return
    
    def _convert_type_to_string(self, sections: list) -> None:
        """递归转换sections中items的type值：0->worksheet, 1->custompage, 2->group"""
        type_mapping = {0: "worksheet", 1: "custompage", 2: "group"}
        
        for section in sections:
            if "items" in section:
                for item in section["items"]:
                    if "type" in item and item["type"] in type_mapping:
                        item["type"] = type_mapping[item["type"]]
            
            if "childSections" in section:
                self._convert_type_to_string(section["childSections"])

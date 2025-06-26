from collections.abc import Generator
from typing import Any
import json
import httpx
import traceback

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class UpdateWorksheetRecordTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        appkey = tool_parameters.get('appkey', '')
        if not appkey:
            yield self.create_json_message({'error': 'Invalid parameter App Key'})
            return
        sign = tool_parameters.get('sign', '')
        if not sign:
            yield self.create_json_message({'error': 'Invalid parameter Sign'})
            return
        worksheet_id = tool_parameters.get('worksheet_id', '')
        if not worksheet_id:
            yield self.create_json_message({'error': 'Invalid parameter Worksheet ID'})
            return
        row_id = tool_parameters.get('row_id', '')
        if not row_id:
            yield self.create_json_message({'error': 'Invalid parameter Record Row ID'})
            return
        record_data = tool_parameters.get('record_data', '')
        if not record_data:
            yield self.create_json_message({'error': 'Invalid parameter Record Row Data'})
            return
        
        host = tool_parameters.get('host', '')
        if not host:
            host = 'https://api.mingdao.com'
        elif not host.startswith(("http://", "https://")):
            yield self.create_json_message({'error': 'Invalid parameter Host Address'})
            return
        else:
            host = f"{host[:-1] if host.endswith('/') else host}/api"

        url = f"{host}/v2/open/worksheet/editRow"
        headers = {'Content-Type': 'application/json'}
        payload = {"appKey": appkey, "sign": sign, "worksheetId": worksheet_id, "rowId": row_id}

        try:
            payload['controls'] = json.loads(record_data)
            res = httpx.post(url, headers=headers, json=payload, timeout=60)
            res.raise_for_status()
            res_json = res.json()
            if res_json.get('error_code') != 1:
                yield self.create_json_message({'error': f"Failed to update the record. {res_json['error_msg']}"})
            else:
                yield self.create_json_message({'result': "Record updated successfully."})
        except httpx.RequestError as e:
            error_msg = f"Failed to update the record, request error: {e}\nStack trace:\n{traceback.format_exc()}"
            yield self.create_json_message({'error': error_msg})
        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse JSON response: {e}\nStack trace:\n{traceback.format_exc()}"
            yield self.create_json_message({'error': error_msg})
        except Exception as e:
            error_msg = f"Failed to update the record, unexpected error: {e}\nStack trace:\n{traceback.format_exc()}"
            yield self.create_json_message({'error': error_msg})

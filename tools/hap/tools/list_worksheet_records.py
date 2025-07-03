from collections.abc import Generator
from typing import Any
import json
import re
import httpx
import traceback

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class ListWorksheetRecordsTool(Tool):
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

        host = tool_parameters.get('host', '')
        if not host:
            host = 'https://api.mingdao.com'
        elif not (host.startswith("http://") or host.startswith("https://")):
            yield self.create_json_message({'error': 'Invalid parameter Host Address'})
            return
        else:
            host = f"{host[:-1] if host.endswith('/') else host}/api"
        
        url_fields = f"{host}/v2/open/worksheet/getWorksheetInfo"
        headers = {'Content-Type': 'application/json'}
        payload = {"appKey": appkey, "sign": sign, "worksheetId": worksheet_id}

        field_ids = tool_parameters.get('field_ids', '')

        try:
            res = httpx.post(url_fields, headers=headers, json=payload, timeout=30)
            res_json = res.json()
            if res.is_success:
                if res_json.get('error_code') != 1:
                    error_msg = res_json.get('error_msg', 'Unknown error')
                    yield self.create_json_message({'error': f"Failed to get the worksheet information. {error_msg}"})
                    return
                else:
                    data = res_json.get('data', {})
                    worksheet_name = data.get('name', 'Unknown Worksheet')
                    controls = data.get('controls', [])
                    fields, schema, table_header = self.get_schema(controls, field_ids)
            else:
                yield self.create_json_message({'error': f"Failed to get the worksheet information, status code: {res.status_code}, response: {res.text}"})
                return
        except Exception as e:
            error_msg = f"Failed to get the worksheet information, something went wrong: {e}\nStack trace:\n{traceback.format_exc()}"
            yield self.create_json_message({'error': error_msg})
            return

        # 处理 field_ids
        if field_ids:
            payload['controls'] = [v.strip() for v in field_ids.split(',') if v.strip()]
            if 'rowid' not in payload['controls']:
                payload['controls'].append('rowid')
            if 'ctime' not in payload['controls']:
                payload['controls'].append('ctime')
        
        # 处理 filters
        filters = tool_parameters.get('filters', '')
        if filters:
            try:
                filters_parsed = json.loads(filters)
                if filters_parsed:
                    payload['filters'] = filters_parsed
            except json.JSONDecodeError:
                yield self.create_json_message({'error': 'Invalid filters JSON format'})
                return
        
        # 处理排序参数
        sort_id = tool_parameters.get('sort_id', '')
        if sort_id:
            payload['sortId'] = sort_id
            sort_is_asc = tool_parameters.get('sort_is_asc', False)
            payload['isAsc'] = bool(sort_is_asc)
        
        # 处理分页参数
        try:
            limit = int(tool_parameters.get('limit', 50))
            limit = max(1, min(limit, 1000))  # 限制在 1-1000 之间
            payload['pageSize'] = limit
        except (ValueError, TypeError):
            payload['pageSize'] = 50
        
        try:
            page_index = int(tool_parameters.get('page_index', 1))
            page_index = max(1, page_index)  # 最小为 1
            payload['pageIndex'] = page_index
        except (ValueError, TypeError):
            payload['pageIndex'] = 1
        
        payload['useControlId'] = True
        payload['listType'] = 1

        url = f"{host}/v2/open/worksheet/getFilterRows"
        try:
            res = httpx.post(url, headers=headers, json=payload, timeout=90)
            res_json = res.json()
            if res.is_success:
                if res_json.get('error_code') != 1:
                    error_msg = res_json.get('error_msg', 'Unknown error')
                    yield self.create_json_message({'error': f"Failed to get the records. {error_msg}"})
                else:
                    data = res_json.get("data", {})
                    result = {
                        "fields": fields,
                        "rows": [],
                        "total": data.get("total", 0),
                        "payload": {key: payload[key] for key in ['worksheetId', 'controls', 'filters', 'sortId', 'isAsc', 'pageSize', 'pageIndex'] if key in payload}
                    }
                    rows = data.get("rows", [])
                    result_type = tool_parameters.get('result_type', '')
                    if not result_type: result_type = 'table'
                    if result_type == 'json':
                        for row in rows:
                            result['rows'].append(self.get_row_field_value(row, schema))
                        yield self.create_json_message({'result': result})
                    else:
                        result_text = f"Found {result['total']} rows in worksheet \"{worksheet_name}\"."
                        if result['total'] > 0:
                            result_text += f" The following are {result['total'] if result['total'] < limit else limit} pieces of data presented in a table format:\n\n{table_header}"
                            for row in rows:
                                result_values = []
                                for f in fields:
                                    field_id = f.get('fieldId', '')
                                    value = row.get(field_id, '')
                                    result_values.append(self.handle_value_type(value, schema.get(field_id, {})))
                                result_text += '\n|'+'|'.join(result_values)+'|'
                        yield self.create_json_message({'result': result_text})
            else:
                yield self.create_json_message({'error': f"Failed to get the records, status code: {res.status_code}, response: {res.text}"})
        except Exception as e:
            error_msg = f"Failed to get the records, something went wrong: {e}\nStack trace:\n{traceback.format_exc()}"
            yield self.create_json_message({'error': error_msg})

    def get_row_field_value(self, row: dict, schema: dict):
        row_value = {"rowid": row.get("rowid", "")}
        for field in schema:
            row_value[field] = self.handle_value_type(row.get(field, ''), schema.get(field, {}))
        return row_value

    def get_schema(self, controls: list, fieldids: str): 
        allow_fields = {v.strip() for v in fieldids.split(',') if v.strip()} if fieldids else set()
        fields = []
        schema = {}
        field_names = []
        for control in controls:
            control_id = control.get('controlId', '')
            control_name = control.get('controlName', '')
            if not control_id or not control_name:
                continue
                
            control_type_id = self.get_real_type_id(control)
            if (control_type_id in self._get_ignore_types()) or (allow_fields and control_id not in allow_fields):
                continue
            else:
                fields.append({'fieldId': control_id, 'fieldName': control_name})
                schema[control_id] = {'typeId': control_type_id, 'options': self.set_option(control)}
                field_names.append(control_name)
        if (not allow_fields or ('ctime' in allow_fields)):
            fields.append({'fieldId': 'ctime', 'fieldName': 'Created Time'})
            schema['ctime'] = {'typeId': 16, 'options': {}}
            field_names.append("Created Time")
        fields.append({'fieldId':'rowid', 'fieldName': 'Record Row ID'})
        schema['rowid'] = {'typeId': 2, 'options': {}}
        field_names.append("Record Row ID")
        return fields, schema, '|'+'|'.join(field_names)+'|\n|'+'---|'*len(field_names)
    
    def get_real_type_id(self, control: dict) -> int:
        control_type = control.get('type', 0)
        if control_type == 30:
            return control.get('sourceControlType', control_type)
        return control_type
    
    def set_option(self, control: dict) -> dict:
        options = {}
        if control.get('options'):
            for option in control['options']:
                key = option.get('key', '')
                value = option.get('value', '')
                if key:
                    options[key] = value
        elif control.get('advancedSetting', {}).get('itemnames'):
            try:
                itemnames = json.loads(control['advancedSetting']['itemnames'])
                for item in itemnames:
                    key = item.get('key', '')
                    value = item.get('value', '')
                    if key:
                        options[key] = value
            except json.JSONDecodeError:
                pass
        return options

    def _get_ignore_types(self):
        return {14, 21, 22, 34, 42, 43, 45, 47, 49, 10010}
    
    def handle_value_type(self, value, field):
        type_id = field.get("typeId")
        if type_id == 10:
            value = value if isinstance(value, str) else "、".join(value) if isinstance(value, (list, tuple)) else str(value)
        elif type_id in [28, 36]:
            value = field.get("options", {}).get(value, value)
        elif type_id in [26, 27, 48, 14]:
            value = self.process_value(value)
        elif type_id in [35, 29]:
            value = self.parse_cascade_or_associated(field, value)
        elif type_id == 40:
            value = self.parse_location(value)
        return self.rich_text_to_plain_text(value) if value else ''

    def process_value(self, value):
        if isinstance(value, str):
            if value.startswith("[{\"accountId\""):
                try:
                    parsed_value = json.loads(value)
                    if isinstance(parsed_value, list):
                        value = ', '.join([item.get('fullname', '') for item in parsed_value if isinstance(item, dict)])
                except json.JSONDecodeError:
                    value = ''
            elif value.startswith("[{\"departmentId\""):
                try:
                    parsed_value = json.loads(value)
                    if isinstance(parsed_value, list):
                        value = '、'.join([item.get('departmentName', '') for item in parsed_value if isinstance(item, dict)])
                except json.JSONDecodeError:
                    value = ''
            elif value.startswith("[{\"organizeId\""):
                try:
                    parsed_value = json.loads(value)
                    if isinstance(parsed_value, list):
                        value = '、'.join([item.get('organizeName', '') for item in parsed_value if isinstance(item, dict)])
                except json.JSONDecodeError:
                    value = ''
            elif value.startswith("[{\"file_id\""):
                value = ''
            elif value == '[]':
                value = ''
        elif hasattr(value, 'accountId'):
            value = getattr(value, 'fullname', str(value))
        return value

    def parse_cascade_or_associated(self, field, value):
        type_id = field.get('typeId')
        if not isinstance(value, str) or not value:
            return ''
            
        if (type_id == 35 and value.startswith('[')) or (type_id == 29 and value.startswith('[{')):
            try:
                parsed_value = json.loads(value)
                if isinstance(parsed_value, list) and len(parsed_value) > 0:
                    first_item = parsed_value[0]
                    if isinstance(first_item, dict):
                        return first_item.get('name', '')
            except json.JSONDecodeError:
                pass
        return ''

    def parse_location(self, value):
        if isinstance(value, str) and len(value) > 10:
            try:
                parsed_value = json.loads(value)
                if isinstance(parsed_value, dict):
                    return parsed_value.get("address", "")
            except json.JSONDecodeError:
                pass
        return ""

    def rich_text_to_plain_text(self, rich_text):
        if not rich_text:
            return ''
        if not isinstance(rich_text, str):
            rich_text = str(rich_text)
        text = re.sub(r'<[^>]+>', '', rich_text) if '<' in rich_text else rich_text
        return text.replace("|", "▏").replace("\n", " ") 
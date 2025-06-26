from collections.abc import Generator
from typing import Any
import json
import httpx
import traceback

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

class GetWorksheetFieldsTool(Tool):
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
        elif not host.startswith(("http://", "https://")):
            yield self.create_json_message({'error': 'Invalid parameter Host Address'})
            return
        else:
            host = f"{host[:-1] if host.endswith('/') else host}/api"

        url = f"{host}/v2/open/worksheet/getWorksheetInfo"
        headers = {'Content-Type': 'application/json'}
        payload = {"appKey": appkey, "sign": sign, "worksheetId": worksheet_id}

        try:
            res = httpx.post(url, headers=headers, json=payload, timeout=60)
            res.raise_for_status()
            res_json = res.json()
            
            # 验证响应结构
            if not isinstance(res_json, dict):
                yield self.create_json_message({'error': 'Invalid response format'})
                return
                
            if res_json.get('error_code') != 1:
                error_msg = res_json.get('error_msg', 'Unknown error')
                yield self.create_json_message({'error': f"Failed to get the worksheet information. {error_msg}"})
            else:
                # 安全访问data和controls
                data = res_json.get('data', {})
                if not isinstance(data, dict):
                    yield self.create_json_message({'error': 'Invalid data structure in response'})
                    return
                    
                controls = data.get('controls', [])
                if not isinstance(controls, list):
                    yield self.create_json_message({'error': 'Invalid controls structure in response'})
                    return
                    
                fields_json, fields_table = self.get_controls(controls)
                result_type = tool_parameters.get('result_type', 'table')
                if result_type == 'json':
                    yield self.create_json_message({'result': fields_json})
                else:
                    yield self.create_json_message({'result': fields_table})
        except httpx.RequestError as e:
            error_msg = f"Failed to get the worksheet information, request error: {e}\nStack trace:\n{traceback.format_exc()}"
            yield self.create_json_message({'error': error_msg})
        except json.JSONDecodeError as e:
            error_msg = f"Failed to parse JSON response: {e}\nStack trace:\n{traceback.format_exc()}"
            yield self.create_json_message({'error': error_msg})
        except Exception as e:
            error_msg = f"Failed to get the worksheet information, unexpected error: {e}\nStack trace:\n{traceback.format_exc()}"
            yield self.create_json_message({'error': error_msg})

    def get_field_type_by_id(self, field_type_id: int) -> str:
        field_type_map = {
            2: "Text",
            3: "Text-Phone",
            4: "Text-Phone",
            5: "Text-Email",
            6: "Number",
            7: "Text",
            8: "Number",
            9: "Option-Single Choice",
            10: "Option-Multiple Choices",
            11: "Option-Single Choice",
            15: "Date",
            16: "Date",
            24: "Option-Region",
            25: "Text",
            26: "Option-Member",
            27: "Option-Department",
            28: "Number",
            29: "Option-Linked Record",
            30: "Unknown Type",
            31: "Number",
            32: "Text",
            33: "Text",
            35: "Option-Linked Record",
            36: "Number-Yes1/No0",
            37: "Number",
            38: "Date",
            40: "Location",
            41: "Text",
            46: "Time",
            48: "Option-Organizational Role",
            50: "Text",
            51: "Query Record",
        }
        return field_type_map.get(field_type_id, '')

    def get_controls(self, controls: list) -> dict:
        fields = []
        fields_list = ['|fieldId|fieldName|fieldType|fieldTypeId|description|options|','|'+'---|'*6]
        for control in controls:
            if not isinstance(control, dict):
                continue
            if 'type' not in control:
                continue
                
            if control['type'] in self._get_ignore_types():
                continue
            field_type_id = control['type']
            field_type = self.get_field_type_by_id(control['type'])
            if field_type_id == 30:
                source_control = control.get('sourceControl', {})
                if not isinstance(source_control, dict) or 'type' not in source_control:
                    continue
                source_type = source_control['type']
                if source_type in self._get_ignore_types():
                    continue
                else:
                    field_type_id = source_type
                    field_type = self.get_field_type_by_id(source_type)
            
            field_id = control.get('controlId', '')
            field_name = control.get('controlName', '')
            field_description = control.get('remark', '').replace('\n', ' ').replace('\t', '  ')
            
            field = {
                'id': field_id,
                'name': field_name,
                'type': field_type,
                'typeId': field_type_id,
                'description': field_description,
                'options': self._extract_options(control),
            }
            fields.append(field)
            fields_list.append(f"|{field['id']}|{field['name']}|{field['type']}|{field['typeId']}|{field['description']}|{field['options'] if field['options'] else ''}|")

        fields.append({
            'id': 'ctime',
            'name': 'Created Time',
            'type': self.get_field_type_by_id(16),
            'typeId': 16,
            'description': '',
            'options': []
        })
        fields_list.append("|ctime|Created Time|Date|16|||")
        return fields, '\n'.join(fields_list)

    def _extract_options(self, control: dict) -> list:
        options = []
        if not isinstance(control, dict) or 'type' not in control:
            return options
            
        control_type = control['type']
        
        if control_type in [9, 10, 11]:
            control_options = control.get('options', [])
            if isinstance(control_options, list):
                options.extend([{"key": opt.get('key', ''), "value": opt.get('value', '')} 
                              for opt in control_options 
                              if isinstance(opt, dict) and 'key' in opt and 'value' in opt])
        elif control_type in [28, 36]:
            advanced_setting = control.get('advancedSetting', {})
            if isinstance(advanced_setting, dict):
                itemnames = advanced_setting.get('itemnames', '')
                if isinstance(itemnames, str) and itemnames.startswith('[{'):
                    try:
                        parsed_options = json.loads(itemnames)
                        if isinstance(parsed_options, list):
                            options = parsed_options
                    except json.JSONDecodeError:
                        pass
        elif control_type in [29, 35]: 
            data_source = control.get('dataSource', '')
            if isinstance(data_source, str) and data_source:
                options.append({"source_worksheet_id": data_source})
        elif control_type == 30:
            source_control = control.get('sourceControl', {})
            if isinstance(source_control, dict) and 'type' in source_control:
                source_type = source_control['type']
                if source_type not in self._get_ignore_types():
                    control_options = control.get('options', [])
                    if isinstance(control_options, list):
                        options.extend([{"key": opt.get('key', ''), "value": opt.get('value', '')} 
                                      for opt in control_options 
                                      if isinstance(opt, dict) and 'key' in opt and 'value' in opt])
        return options
    
    def _get_ignore_types(self):
        return {14, 21, 22, 34, 42, 43, 45, 47, 49, 10010}
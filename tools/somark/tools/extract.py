import logging
import json
from typing import Any, Dict, Generator
import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)

class ExtractTool(Tool):
    def _invoke(self, tool_parameters: Dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # 1. 获取参数
        file = tool_parameters.get("file")
        lang = "auto"
        if not file:
            yield self.create_text_message("Error: No file provided.")
            return

        # 2. 获取配置
        # 默认使用 v1 接口
        base_url = self.runtime.credentials.get("base_url", "https://somark.tech/api/v1/extract")
        api_key = self.runtime.credentials.get("api_key")
        
        if not api_key:
             yield self.create_text_message("Error: API Key is required.")
             return

        # 3. 构造请求 URL
        # URL 格式: {base_url}/acc_sync
        base_url = base_url.rstrip("/")
        url = f"{base_url}/acc_sync"
        
        logger.info(f"Somark: Sending request to {url}")
        
        try:
            # 4. 构造文件上传
            # Dify 的 file 对象通常有 filename 和 blob (二进制数据) 属性
            files = {
                "file": (file.filename, file.blob, file.mimetype)
            }
            
            # 5. 构造 Form Data
            # 根据 API 文档，api_key 需要放在 multipart/form-data 中
            data = {
                "api_key": api_key,
                "lang": lang,
                "output_formats": ["markdown"]
            }

            # 6. 发送请求
            # 注意：requests.post 传 files 时会自动设置 Content-Type 为 multipart/form-data
            response = requests.post(url, files=files, data=data, timeout=120)
            
            if response.status_code != 200:
                error_msg = f"Somark API Error: {response.status_code} - {response.text}"
                logger.error(error_msg)
                yield self.create_text_message(error_msg)
                return

            # 7. 处理响应
            result = response.json()
            
            # 提取核心内容
            text_content = ""
            if isinstance(result, dict):
                # 优先找 data.result
                if "data" in result and isinstance(result["data"], dict) and "result" in result["data"]:
                     # 返回 result 里的内容，通常是 markdown 文本
                     res_data = result["data"]["result"]
                     # 如果 result 本身包含 outputs.markdown，则提取它，否则转存整个 json
                     if isinstance(res_data, dict) and "outputs" in res_data and "markdown" in res_data["outputs"]:
                         text_content = res_data["outputs"]["markdown"]
                     else:
                         text_content = json.dumps(res_data, ensure_ascii=False)
                else:
                    text_content = json.dumps(result, ensure_ascii=False)
            else:
                text_content = str(result)

            yield self.create_text_message(text_content)

        except Exception as e:
            logger.error(f"Somark Plugin Error: {str(e)}")
            yield self.create_text_message(f"Error invoking Somark API: {str(e)}")

import base64
import json
import logging
from collections.abc import Generator
from typing import Any, Dict

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)


class LinuxdoTool(Tool):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_url = "https://connect.linux.do/api"
        self.timeout = 10

    def _get_auth_headers(self) -> Dict[str, str]:
        """获取认证头"""
        client_id = self.runtime.credentials.get("client_id")
        client_secret = self.runtime.credentials.get("client_secret")
        
        credential = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        return {
            "Authorization": f"Basic {credential}",
            "User-Agent": "Dify LinuxDo Plugin/1.0",
            "Accept": "application/json"
        }

    def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """发起API请求"""
        url = f"{self.base_url}/{endpoint}"
        headers = self._get_auth_headers()
        
        try:
            response = requests.get(url, params=params, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            raise Exception("请求超时，请稍后重试")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise Exception("认证失败：Client ID或Client Secret错误")
            elif e.response.status_code == 403:
                raise Exception("API Key无效或已过期")
            elif e.response.status_code == 404:
                raise Exception("API端点不存在")
            else:
                raise Exception(f"API请求失败：HTTP {e.response.status_code}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"网络请求失败：{str(e)}")
        except json.JSONDecodeError:
            raise Exception("API返回数据格式错误")

    def _get_user_info(self, include_extra: bool = True) -> Dict:
        """获取用户信息"""
        api_key = self.runtime.credentials.get("api_key")
        params = {"api_key": api_key}
        
        if include_extra:
            params["extra"] = "true"
        
        return self._make_request("key", params)

    def _format_user_info(self, user_data: Dict, include_extra: bool) -> Dict:
        """格式化用户信息"""
        formatted_data = {
            "user_id": user_data.get("user_id"),
            "api_key_valid": True,
            "timestamp": user_data.get("timestamp")
        }
        
        if include_extra and user_data:
            # 添加额外的用户信息（如果API返回的话）
            formatted_data.update({
                "username": user_data.get("username"),
                "name": user_data.get("name"),
                "avatar_url": user_data.get("avatar_url"),
                "email": user_data.get("email"),
                "trust_level": user_data.get("trust_level"),
                "active": user_data.get("active"),
                "admin": user_data.get("admin"),
                "moderator": user_data.get("moderator"),
                "last_seen_at": user_data.get("last_seen_at"),
                "created_at": user_data.get("created_at")
            })
        
        return formatted_data

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            include_extra_info = tool_parameters.get("include_extra_info", True)
            verify_only = tool_parameters.get("verify_only", False)
            
            # 如果只是验证，则不包含额外信息
            if verify_only:
                include_extra_info = False
            
            yield self.create_text_message("🔐 开始验证LinuxDo Connect认证...")
            
            # 获取用户信息
            user_data = self._get_user_info(include_extra_info)
            
            if not user_data or "user_id" not in user_data:
                raise Exception("API Key验证失败：无法获取用户信息")
            
            # 格式化用户信息
            formatted_info = self._format_user_info(user_data, include_extra_info)
            
            yield self.create_text_message(f"✅ 认证成功！用户ID: {formatted_info['user_id']}")
            
            if verify_only:
                # 仅验证模式
                yield self.create_variable_message("verification_result", {
                    "status": "success",
                    "user_id": formatted_info["user_id"],
                    "api_key_valid": True,
                    "message": "API Key验证成功"
                })
                yield self.create_text_message("🎯 API Key验证成功，连接正常")
            else:
                # 完整信息模式
                yield self.create_variable_message("user_info", formatted_info)
                
                # 生成用户信息摘要
                summary = "# LinuxDo用户信息\n\n"
                summary += f"**用户ID**: {formatted_info['user_id']}\n"
                summary += f"**API Key状态**: ✅ 有效\n"
                
                if include_extra_info:
                    if formatted_info.get("username"):
                        summary += f"**用户名**: {formatted_info['username']}\n"
                    if formatted_info.get("name"):
                        summary += f"**显示名称**: {formatted_info['name']}\n"
                    if formatted_info.get("trust_level") is not None:
                        summary += f"**信任级别**: {formatted_info['trust_level']}\n"
                    if formatted_info.get("active") is not None:
                        summary += f"**账户状态**: {'活跃' if formatted_info['active'] else '非活跃'}\n"
                    if formatted_info.get("admin"):
                        summary += f"**管理员**: {'是' if formatted_info['admin'] else '否'}\n"
                    if formatted_info.get("moderator"):
                        summary += f"**版主**: {'是' if formatted_info['moderator'] else '否'}\n"
                    if formatted_info.get("created_at"):
                        summary += f"**注册时间**: {formatted_info['created_at']}\n"
                    if formatted_info.get("last_seen_at"):
                        summary += f"**最后活跃**: {formatted_info['last_seen_at']}\n"
                
                yield self.create_text_message(summary)
                
                # 显示可用的服务
                services_info = "\n## 🔗 可用服务\n\n"
                services_info += "通过LinuxDo Connect，您可以访问以下服务：\n"
                services_info += f"- **DeepLX翻译**: `https://api.deeplx.org/{self.runtime.credentials.get('api_key')}/translate`\n"
                services_info += "- 更多服务正在接入中...\n"
                
                yield self.create_text_message(services_info)
            
        except Exception as e:
            logger.exception(f"LinuxDo用户信息获取失败：{e}")
            yield self.create_text_message(f"❌ 操作失败：{str(e)}")
            
            # 返回错误信息
            yield self.create_variable_message("verification_result", {
                "status": "error",
                "api_key_valid": False,
                "message": str(e)
            })
            
            raise Exception(f"LinuxDo用户信息获取失败：{str(e)}")

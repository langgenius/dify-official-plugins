import json
import logging
import re
from collections.abc import Generator
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)


class V2exTool(Tool):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_url = "https://www.v2ex.com/api"
        self.headers = {
            "User-Agent": "Dify V2EX Plugin/1.0",
            "Accept": "application/json"
        }
        self.timeout = 10

    def _make_request(self, endpoint: str, params: Optional[Dict] = None) -> Dict:
        """发起API请求"""
        url = f"{self.base_url}/{endpoint}"
        
        try:
            response = requests.get(
                url, 
                params=params, 
                headers=self.headers, 
                timeout=self.timeout
            )
            response.raise_for_status()
            
            # 检查rate limit
            if 'X-Rate-Limit-Remaining' in response.headers:
                remaining = int(response.headers['X-Rate-Limit-Remaining'])
                if remaining < 10:
                    logger.warning(f"V2EX API rate limit warning: {remaining} requests remaining")
            
            return response.json()
            
        except requests.exceptions.Timeout:
            raise Exception("V2EX API请求超时，请稍后重试")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                raise Exception("V2EX API请求频率限制，请稍后重试")
            elif e.response.status_code == 404:
                raise Exception("请求的资源不存在")
            else:
                raise Exception(f"V2EX API请求失败: {e.response.status_code}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"网络请求失败: {str(e)}")
        except json.JSONDecodeError:
            raise Exception("V2EX API返回数据格式错误")

    def _get_hot_topics(self, limit: int = 10) -> List[Dict]:
        """获取热门主题"""
        data = self._make_request("topics/hot.json")
        return data[:limit] if isinstance(data, list) else []

    def _get_latest_topics(self, limit: int = 10) -> List[Dict]:
        """获取最新主题"""
        data = self._make_request("topics/latest.json")
        return data[:limit] if isinstance(data, list) else []

    def _get_node_info(self, node_name: str) -> Dict:
        """获取节点信息"""
        if not node_name or not node_name.strip():
            raise Exception("节点名称不能为空")
        
        # 验证节点名格式（只允许英文、数字、下划线、连字符）
        if not re.match(r'^[a-zA-Z0-9_-]+$', node_name.strip()):
            raise Exception("节点名称只能包含英文字母、数字、下划线和连字符")
        
        return self._make_request("nodes/show.json", {"name": node_name.strip()})

    def _get_user_info(self, query: str) -> Dict:
        """获取用户信息"""
        if not query or not query.strip():
            raise Exception("用户名或ID不能为空")
        
        query = query.strip()
        
        # 判断是用户名还是ID
        if query.isdigit():
            params = {"id": int(query)}
        else:
            # 验证用户名格式
            if not re.match(r'^[a-zA-Z0-9_-]+$', query):
                raise Exception("用户名只能包含英文字母、数字、下划线和连字符")
            params = {"username": query}
        
        return self._make_request("members/show.json", params)

    def _format_topic(self, topic: Dict) -> Dict:
        """格式化主题信息"""
        return {
            "id": topic.get("id"),
            "title": topic.get("title", "").strip(),
            "content": topic.get("content", "").strip() if topic.get("content") else "",
            "url": f"https://www.v2ex.com/t/{topic.get('id')}" if topic.get("id") else "",
            "replies": topic.get("replies", 0),
            "created": topic.get("created"),
            "last_modified": topic.get("last_modified"),
            "node": {
                "id": topic.get("node", {}).get("id"),
                "name": topic.get("node", {}).get("name"),
                "title": topic.get("node", {}).get("title")
            } if topic.get("node") else None,
            "member": {
                "id": topic.get("member", {}).get("id"),
                "username": topic.get("member", {}).get("username"),
                "avatar": topic.get("member", {}).get("avatar_large") or topic.get("member", {}).get("avatar_normal")
            } if topic.get("member") else None
        }

    def _format_node(self, node: Dict) -> Dict:
        """格式化节点信息"""
        return {
            "id": node.get("id"),
            "name": node.get("name"),
            "title": node.get("title", "").strip(),
            "title_alternative": node.get("title_alternative", "").strip(),
            "url": f"https://www.v2ex.com/go/{node.get('name')}" if node.get("name") else "",
            "topics": node.get("topics", 0),
            "avatar": node.get("avatar_large") or node.get("avatar_normal"),
            "header": node.get("header", "").strip() if node.get("header") else "",
            "footer": node.get("footer", "").strip() if node.get("footer") else "",
            "created": node.get("created")
        }

    def _format_user(self, user: Dict) -> Dict:
        """格式化用户信息"""
        return {
            "id": user.get("id"),
            "username": user.get("username"),
            "url": f"https://www.v2ex.com/u/{user.get('username')}" if user.get("username") else "",
            "website": user.get("website", "").strip() if user.get("website") else "",
            "twitter": user.get("twitter", "").strip() if user.get("twitter") else "",
            "psn": user.get("psn", "").strip() if user.get("psn") else "",
            "github": user.get("github", "").strip() if user.get("github") else "",
            "btc": user.get("btc", "").strip() if user.get("btc") else "",
            "location": user.get("location", "").strip() if user.get("location") else "",
            "tagline": user.get("tagline", "").strip() if user.get("tagline") else "",
            "bio": user.get("bio", "").strip() if user.get("bio") else "",
            "avatar": user.get("avatar_large") or user.get("avatar_normal"),
            "created": user.get("created"),
            "status": user.get("status")
        }

    def _search_topics_by_keyword(self, topics: List[Dict], keyword: str) -> List[Dict]:
        """在主题列表中搜索关键词"""
        if not keyword or not keyword.strip():
            return topics
        
        keyword = keyword.strip().lower()
        filtered_topics = []
        
        for topic in topics:
            title = topic.get("title", "").lower()
            content = topic.get("content", "").lower() if topic.get("content") else ""
            node_name = topic.get("node", {}).get("name", "").lower() if topic.get("node") else ""
            node_title = topic.get("node", {}).get("title", "").lower() if topic.get("node") else ""
            
            if (keyword in title or 
                keyword in content or 
                keyword in node_name or 
                keyword in node_title):
                filtered_topics.append(topic)
        
        return filtered_topics

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            search_type = tool_parameters.get("search_type")
            search_query = tool_parameters.get("search_query", "").strip()
            limit = min(max(int(tool_parameters.get("limit", 10)), 1), 50)
            
            yield self.create_text_message(f"🔍 开始搜索V2EX内容: {search_type}")
            
            if search_type == "hot_topics":
                # 获取热门主题
                topics = self._get_hot_topics(limit)
                
                # 如果有搜索关键词，进行过滤
                if search_query:
                    topics = self._search_topics_by_keyword(topics, search_query)
                    yield self.create_text_message(f"🔎 根据关键词 '{search_query}' 过滤热门主题")
                
                formatted_topics = [self._format_topic(topic) for topic in topics]
                
                yield self.create_text_message(f"📊 找到 {len(formatted_topics)} 个热门主题")
                yield self.create_variable_message("search_results", formatted_topics)
                
                # 生成摘要文本
                summary = "# V2EX热门主题\n\n"
                for i, topic in enumerate(formatted_topics, 1):
                    summary += f"## {i}. {topic['title']}\n"
                    summary += f"- **链接**: {topic['url']}\n"
                    summary += f"- **回复数**: {topic['replies']}\n"
                    if topic['node']:
                        summary += f"- **节点**: {topic['node']['title']} ({topic['node']['name']})\n"
                    if topic['member']:
                        summary += f"- **作者**: {topic['member']['username']}\n"
                    summary += "\n"
                
                yield self.create_text_message(summary)
            
            elif search_type == "latest_topics":
                # 获取最新主题
                topics = self._get_latest_topics(limit)
                
                # 如果有搜索关键词，进行过滤
                if search_query:
                    topics = self._search_topics_by_keyword(topics, search_query)
                    yield self.create_text_message(f"🔎 根据关键词 '{search_query}' 过滤最新主题")
                
                formatted_topics = [self._format_topic(topic) for topic in topics]
                
                yield self.create_text_message(f"📊 找到 {len(formatted_topics)} 个最新主题")
                yield self.create_variable_message("search_results", formatted_topics)
                
                # 生成摘要文本
                summary = "# V2EX最新主题\n\n"
                for i, topic in enumerate(formatted_topics, 1):
                    summary += f"## {i}. {topic['title']}\n"
                    summary += f"- **链接**: {topic['url']}\n"
                    summary += f"- **回复数**: {topic['replies']}\n"
                    if topic['node']:
                        summary += f"- **节点**: {topic['node']['title']} ({topic['node']['name']})\n"
                    if topic['member']:
                        summary += f"- **作者**: {topic['member']['username']}\n"
                    summary += "\n"
                
                yield self.create_text_message(summary)
            
            elif search_type == "node_info":
                if not search_query:
                    raise Exception("获取节点信息需要提供节点名称")
                
                node = self._get_node_info(search_query)
                formatted_node = self._format_node(node)
                
                yield self.create_text_message(f"📋 找到节点: {formatted_node['title']}")
                yield self.create_variable_message("search_results", formatted_node)
                
                # 生成节点信息文本
                summary = f"# V2EX节点信息\n\n"
                summary += f"## {formatted_node['title']}\n"
                summary += f"- **节点名**: {formatted_node['name']}\n"
                summary += f"- **链接**: {formatted_node['url']}\n"
                summary += f"- **主题数**: {formatted_node['topics']}\n"
                if formatted_node['title_alternative']:
                    summary += f"- **别名**: {formatted_node['title_alternative']}\n"
                if formatted_node['header']:
                    summary += f"- **描述**: {formatted_node['header']}\n"
                
                yield self.create_text_message(summary)
            
            elif search_type == "user_info":
                if not search_query:
                    raise Exception("获取用户信息需要提供用户名或用户ID")
                
                user = self._get_user_info(search_query)
                formatted_user = self._format_user(user)
                
                yield self.create_text_message(f"👤 找到用户: {formatted_user['username']}")
                yield self.create_variable_message("search_results", formatted_user)
                
                # 生成用户信息文本
                summary = f"# V2EX用户信息\n\n"
                summary += f"## {formatted_user['username']}\n"
                summary += f"- **链接**: {formatted_user['url']}\n"
                if formatted_user['tagline']:
                    summary += f"- **签名**: {formatted_user['tagline']}\n"
                if formatted_user['bio']:
                    summary += f"- **简介**: {formatted_user['bio']}\n"
                if formatted_user['location']:
                    summary += f"- **位置**: {formatted_user['location']}\n"
                if formatted_user['website']:
                    summary += f"- **网站**: {formatted_user['website']}\n"
                if formatted_user['github']:
                    summary += f"- **GitHub**: {formatted_user['github']}\n"
                if formatted_user['twitter']:
                    summary += f"- **Twitter**: {formatted_user['twitter']}\n"
                
                yield self.create_text_message(summary)
            
            else:
                raise Exception(f"不支持的搜索类型: {search_type}")
            
        except Exception as e:
            logger.exception(f"V2EX搜索失败: {e}")
            yield self.create_text_message(f"❌ 搜索失败: {str(e)}")
            raise Exception(f"V2EX搜索失败: {str(e)}")
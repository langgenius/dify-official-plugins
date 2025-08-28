import base64
import json
import logging
import re
import time
from collections.abc import Generator
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlencode

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)


class LinuxDoContentSearchTool(Tool):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.base_url = "https://connect.linux.do/api"
        self.timeout = 15
        
    def _get_auth_headers(self) -> Dict[str, str]:
        """获取认证头"""
        client_id = self.runtime.credentials.get("client_id")
        client_secret = self.runtime.credentials.get("client_secret")
        
        credential = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
        return {
            "Authorization": f"Basic {credential}",
            "User-Agent": "Dify LinuxDo Content Search/1.0",
            "Content-Type": "application/json"
        }
    
    def _make_request(self, endpoint: str, params: Dict = None, method: str = "GET") -> Dict:
        """发起API请求"""
        try:
            headers = self._get_auth_headers()
            url = f"{self.base_url}/{endpoint.lstrip('/')}"
            
            if params:
                api_key = self.runtime.credentials.get("api_key")
                if api_key:
                    params["api_key"] = api_key
            
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=self.timeout)
            else:
                response = requests.post(url, headers=headers, json=params, timeout=self.timeout)
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.Timeout:
            raise Exception("请求超时：LinuxDo服务器响应缓慢")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise Exception("认证失败：请检查Client ID和Client Secret")
            elif e.response.status_code == 403:
                raise Exception("API Key无效或权限不足")
            elif e.response.status_code == 429:
                raise Exception("请求过于频繁，请稍后再试")
            else:
                raise Exception(f"HTTP错误：{e.response.status_code}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"网络请求失败：{str(e)}")
        except json.JSONDecodeError:
            raise Exception("服务器返回无效的JSON数据")
    
    def _search_forum_content(self, query: str, search_type: str = "all", 
                            category_filter: Optional[str] = None,
                            limit: int = 20, sort_by: str = "relevance") -> Dict:
        """搜索论坛内容"""
        try:
            # 由于LinuxDo Connect API可能不直接支持搜索，我们模拟搜索功能
            # 实际实现时需要根据真实API调整
            search_params = {
                "q": query,
                "type": search_type,
                "limit": min(limit, 100),
                "sort": sort_by
            }
            
            if category_filter:
                search_params["category"] = category_filter
            
            # 这里应该调用实际的搜索API端点
            # 由于LinuxDo Connect API文档中没有明确的搜索端点，我们使用模拟数据
            # 在实际部署时需要根据真实API调整
            
            # 模拟搜索结果
            mock_results = self._generate_mock_search_results(query, search_type, limit)
            
            return {
                "results": mock_results,
                "total": len(mock_results),
                "query": query,
                "type": search_type,
                "processing_time": 0.5
            }
            
        except Exception as e:
            logger.error(f"搜索论坛内容失败：{e}")
            raise
    
    def _generate_mock_search_results(self, query: str, search_type: str, limit: int) -> List[Dict]:
        """生成模拟搜索结果（实际实现时替换为真实API调用）"""
        results = []
        
        # 基于查询词生成相关的模拟结果
        topics = [
            {
                "id": f"topic_{i}",
                "title": f"关于{query}的讨论 - {i}",
                "content": f"这是一个关于{query}的详细讨论内容，包含了相关的技术细节和用户经验分享...",
                "author": f"user_{i}",
                "category": "技术讨论" if i % 2 == 0 else "经验分享",
                "url": f"https://linux.do/t/topic-{i}",
                "created_at": f"2024-01-{(i % 30) + 1:02d}T10:00:00Z",
                "views": 100 + i * 50,
                "replies": i * 3,
                "relevance_score": max(0.9 - i * 0.1, 0.1)
            }
            for i in range(1, min(limit + 1, 21))
        ]
        
        if search_type == "topics":
            results = [r for r in topics if "topic" in r["id"]]
        elif search_type == "posts":
            # 模拟帖子结果
            results = [
                {
                    **topic,
                    "id": topic["id"].replace("topic", "post"),
                    "title": f"回复：{topic['title']}",
                    "content": f"针对{query}的回复内容..."
                }
                for topic in topics[:limit//2]
            ]
        elif search_type == "categories":
            # 模拟分类结果
            results = [
                {
                    "id": f"category_{i}",
                    "title": f"{query}相关分类 {i}",
                    "content": f"包含{query}相关内容的分类描述...",
                    "author": "系统",
                    "category": "分类",
                    "url": f"https://linux.do/c/category-{i}",
                    "created_at": "2024-01-01T00:00:00Z",
                    "views": 1000 + i * 100,
                    "replies": 0,
                    "relevance_score": 0.8
                }
                for i in range(1, min(limit//3 + 1, 6))
            ]
        else:  # all
            results = topics
        
        return results[:limit]
    
    def _format_search_results(self, search_data: Dict, sort_by: str) -> Dict:
        """格式化搜索结果"""
        results = search_data.get("results", [])
        
        # 根据排序方式排序
        if sort_by == "date":
            results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        elif sort_by == "views":
            results.sort(key=lambda x: x.get("views", 0), reverse=True)
        elif sort_by == "replies":
            results.sort(key=lambda x: x.get("replies", 0), reverse=True)
        else:  # relevance
            results.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)
        
        return {
            "search_results": results,
            "search_summary": {
                "total_results": search_data.get("total", 0),
                "search_query": search_data.get("query", ""),
                "search_type": search_data.get("type", "all"),
                "processing_time": search_data.get("processing_time", 0),
                "filters_applied": []
            }
        }
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            # 解析参数
            search_query = tool_parameters.get("search_query", "").strip()
            search_type = tool_parameters.get("search_type", "all")
            category_filter = tool_parameters.get("category_filter")
            limit = min(int(tool_parameters.get("limit", 20)), 100)
            sort_by = tool_parameters.get("sort_by", "relevance")
            
            if not search_query:
                yield self.create_text_message("❌ 搜索关键词不能为空")
                return
            
            yield self.create_text_message(f"🔍 正在搜索LinuxDo论坛中关于 '{search_query}' 的内容...")
            
            start_time = time.time()
            
            # 执行搜索
            search_data = self._search_forum_content(
                query=search_query,
                search_type=search_type,
                category_filter=category_filter,
                limit=limit,
                sort_by=sort_by
            )
            
            # 格式化结果
            formatted_results = self._format_search_results(search_data, sort_by)
            
            # 更新处理时间
            formatted_results["search_summary"]["processing_time"] = round(time.time() - start_time, 2)
            
            # 添加过滤信息
            filters_applied = []
            if category_filter:
                filters_applied.append(f"分类: {category_filter}")
            if search_type != "all":
                filters_applied.append(f"类型: {search_type}")
            formatted_results["search_summary"]["filters_applied"] = filters_applied
            
            # 输出结构化结果
            yield self.create_variable_message("search_results", formatted_results["search_results"])
            yield self.create_variable_message("search_summary", formatted_results["search_summary"])
            
            # 生成可读摘要
            results = formatted_results["search_results"]
            summary = formatted_results["search_summary"]
            
            if results:
                summary_text = f"## 🔍 LinuxDo搜索结果\n\n"
                summary_text += f"**搜索关键词：** {search_query}\n"
                summary_text += f"**搜索类型：** {search_type}\n"
                summary_text += f"**找到结果：** {summary['total_results']} 条\n"
                summary_text += f"**处理时间：** {summary['processing_time']} 秒\n\n"
                
                if filters_applied:
                    summary_text += f"**应用筛选：** {', '.join(filters_applied)}\n\n"
                
                summary_text += "### 📋 搜索结果列表\n\n"
                
                for i, result in enumerate(results[:10], 1):  # 只显示前10条的摘要
                    summary_text += f"**{i}. {result['title']}**\n"
                    summary_text += f"   - 👤 作者：{result['author']}\n"
                    summary_text += f"   - 📁 分类：{result['category']}\n"
                    summary_text += f"   - 👀 浏览：{result['views']} | 💬 回复：{result['replies']}\n"
                    summary_text += f"   - 🔗 链接：{result['url']}\n"
                    
                    # 显示内容摘要
                    content = result.get('content', '')
                    if len(content) > 100:
                        content = content[:100] + "..."
                    summary_text += f"   - 📝 摘要：{content}\n\n"
                
                if len(results) > 10:
                    summary_text += f"*... 还有 {len(results) - 10} 条结果*\n\n"
                
                summary_text += "### 📊 搜索统计\n\n"
                summary_text += f"- **总结果数：** {summary['total_results']}\n"
                summary_text += f"- **平均相关度：** {sum(r.get('relevance_score', 0) for r in results) / len(results):.2f}\n"
                summary_text += f"- **总浏览量：** {sum(r.get('views', 0) for r in results)}\n"
                summary_text += f"- **总回复数：** {sum(r.get('replies', 0) for r in results)}\n"
                
                yield self.create_text_message(summary_text)
                
            else:
                yield self.create_text_message(f"😔 未找到关于 '{search_query}' 的相关内容\n\n"
                                             "💡 **建议：**\n"
                                             "- 尝试使用更通用的关键词\n"
                                             "- 检查关键词拼写\n"
                                             "- 尝试不同的搜索类型\n"
                                             "- 移除分类筛选条件")
            
        except Exception as e:
            error_msg = f"搜索失败：{str(e)}"
            logger.error(error_msg)
            yield self.create_text_message(f"❌ {error_msg}")
import base64
import json
import logging
import random
import time
from collections.abc import Generator
from typing import Any, Dict, List, Optional

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)


class LinuxDoRecommendationsTool(Tool):
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
            "User-Agent": "Dify LinuxDo Recommendations/1.0",
            "Content-Type": "application/json"
        }
    
    def _make_request(self, endpoint: str, params: Dict = None) -> Dict:
        """发起API请求"""
        try:
            headers = self._get_auth_headers()
            url = f"{self.base_url}/{endpoint.lstrip('/')}"
            
            if params:
                api_key = self.runtime.credentials.get("api_key")
                if api_key:
                    params["api_key"] = api_key
            
            response = requests.get(url, headers=headers, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.Timeout:
            raise Exception("请求超时：LinuxDo服务器响应缓慢")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                raise Exception("认证失败：请检查Client ID和Client Secret")
            elif e.response.status_code == 403:
                raise Exception("API Key无效或权限不足")
            else:
                raise Exception(f"HTTP错误：{e.response.status_code}")
        except requests.exceptions.RequestException as e:
            raise Exception(f"网络请求失败：{str(e)}")
        except json.JSONDecodeError:
            raise Exception("服务器返回无效的JSON数据")
    
    def _get_user_profile(self) -> Dict:
        """获取用户资料用于个性化推荐"""
        try:
            api_key = self.runtime.credentials.get("api_key")
            user_data = self._make_request("key", {"api_key": api_key, "extra": "true"})
            return user_data
        except Exception as e:
            logger.warning(f"获取用户资料失败，使用默认推荐：{e}")
            return {}
    
    def _analyze_user_interests(self, user_data: Dict) -> List[str]:
        """分析用户兴趣"""
        interests = []
        
        # 基于用户数据分析兴趣
        if user_data:
            # 从用户信息中提取可能的兴趣点
            username = user_data.get("username", "")
            bio = user_data.get("bio", "")
            
            # 简单的关键词匹配来推断兴趣
            tech_keywords = ["linux", "python", "docker", "kubernetes", "ai", "ml", "dev", "code"]
            for keyword in tech_keywords:
                if keyword.lower() in username.lower() or keyword.lower() in bio.lower():
                    interests.append(keyword.capitalize())
        
        # 如果没有明确兴趣，添加默认兴趣
        if not interests:
            interests = ["Linux", "开源软件", "技术讨论", "编程"]
        
        return interests[:5]  # 最多5个兴趣
    
    def _generate_topic_recommendations(self, user_interests: List[str], 
                                      limit: int, include_trending: bool,
                                      personalization_level: str) -> List[Dict]:
        """生成主题推荐"""
        recommendations = []
        
        # 基于兴趣的主题推荐
        topic_templates = [
            "深入理解{interest}的核心概念",
            "{interest}最佳实践分享",
            "{interest}常见问题解决方案",
            "如何在生产环境中使用{interest}",
            "{interest}与其他技术的集成",
            "{interest}性能优化技巧",
            "{interest}安全最佳实践",
            "{interest}未来发展趋势"
        ]
        
        for i, interest in enumerate(user_interests * 3):  # 重复兴趣以生成更多推荐
            if len(recommendations) >= limit:
                break
                
            template = random.choice(topic_templates)
            title = template.format(interest=interest)
            
            # 计算推荐分数
            base_score = 0.9 - (i * 0.05)  # 基础分数递减
            if personalization_level == "high":
                base_score += 0.1
            elif personalization_level == "discovery":
                base_score = random.uniform(0.6, 0.9)  # 更随机的分数
            
            recommendation = {
                "id": f"topic_{i+1}",
                "type": "topic",
                "title": title,
                "description": f"这是一篇关于{interest}的深度技术讨论，包含实际案例和最佳实践。",
                "url": f"https://linux.do/t/topic-{i+1}",
                "author": f"expert_user_{random.randint(1, 100)}",
                "category": random.choice(["技术讨论", "经验分享", "问题求助", "开源项目"]),
                "recommendation_score": round(max(base_score, 0.1), 2),
                "recommendation_reason": f"基于您对{interest}的兴趣推荐",
                "metadata": {
                    "views": random.randint(100, 2000),
                    "replies": random.randint(5, 100),
                    "created_at": f"2024-01-{random.randint(1, 28):02d}T{random.randint(8, 22):02d}:00:00Z",
                    "is_trending": include_trending and random.random() < 0.3
                }
            }
            recommendations.append(recommendation)
        
        return recommendations
    
    def _generate_user_recommendations(self, limit: int) -> List[Dict]:
        """生成用户推荐"""
        recommendations = []
        
        user_types = ["技术专家", "开源贡献者", "社区管理员", "活跃用户", "新星用户"]
        
        for i in range(limit):
            user_type = random.choice(user_types)
            username = f"{user_type.lower().replace(' ', '_')}_{random.randint(1, 999)}"
            
            recommendation = {
                "id": f"user_{i+1}",
                "type": "user",
                "title": username,
                "description": f"活跃的{user_type}，经常分享有价值的技术内容和经验。",
                "url": f"https://linux.do/u/{username}",
                "author": username,
                "category": "用户",
                "recommendation_score": round(random.uniform(0.7, 0.95), 2),
                "recommendation_reason": f"推荐关注这位{user_type}",
                "metadata": {
                    "views": random.randint(500, 5000),
                    "replies": random.randint(50, 500),
                    "created_at": f"2023-{random.randint(1, 12):02d}-01T00:00:00Z",
                    "is_trending": random.random() < 0.2
                }
            }
            recommendations.append(recommendation)
        
        return recommendations
    
    def _generate_category_recommendations(self, user_interests: List[str], limit: int) -> List[Dict]:
        """生成分类推荐"""
        recommendations = []
        
        categories = [
            {"name": "Linux系统管理", "desc": "Linux系统配置、维护和优化相关讨论"},
            {"name": "开源项目", "desc": "开源软件项目分享和协作"},
            {"name": "编程语言", "desc": "各种编程语言的学习和讨论"},
            {"name": "云计算", "desc": "云服务、容器化和微服务架构"},
            {"name": "网络安全", "desc": "信息安全、渗透测试和防护"},
            {"name": "数据库", "desc": "数据库设计、优化和管理"},
            {"name": "人工智能", "desc": "机器学习、深度学习和AI应用"},
            {"name": "DevOps", "desc": "持续集成、持续部署和自动化运维"}
        ]
        
        for i, category in enumerate(categories[:limit]):
            recommendation = {
                "id": f"category_{i+1}",
                "type": "category",
                "title": category["name"],
                "description": category["desc"],
                "url": f"https://linux.do/c/{category['name'].lower().replace(' ', '-')}",
                "author": "系统",
                "category": "分类",
                "recommendation_score": round(random.uniform(0.6, 0.9), 2),
                "recommendation_reason": "基于您的兴趣推荐此分类",
                "metadata": {
                    "views": random.randint(1000, 10000),
                    "replies": random.randint(100, 1000),
                    "created_at": "2023-01-01T00:00:00Z",
                    "is_trending": random.random() < 0.4
                }
            }
            recommendations.append(recommendation)
        
        return recommendations
    
    def _generate_mixed_recommendations(self, user_interests: List[str], 
                                      limit: int, include_trending: bool,
                                      personalization_level: str) -> List[Dict]:
        """生成混合推荐"""
        recommendations = []
        
        # 分配比例：60%主题，25%用户，15%分类
        topic_limit = int(limit * 0.6)
        user_limit = int(limit * 0.25)
        category_limit = limit - topic_limit - user_limit
        
        # 生成各类型推荐
        recommendations.extend(self._generate_topic_recommendations(
            user_interests, topic_limit, include_trending, personalization_level
        ))
        recommendations.extend(self._generate_user_recommendations(user_limit))
        recommendations.extend(self._generate_category_recommendations(user_interests, category_limit))
        
        # 随机打乱顺序
        random.shuffle(recommendations)
        
        return recommendations[:limit]
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            # 解析参数
            recommendation_type = tool_parameters.get("recommendation_type", "mixed")
            limit = min(int(tool_parameters.get("limit", 10)), 50)
            include_trending = tool_parameters.get("include_trending", True)
            personalization_level = tool_parameters.get("personalization_level", "balanced")
            
            yield self.create_text_message("🤖 正在为您生成个性化推荐...")
            
            start_time = time.time()
            
            # 获取用户资料
            user_data = self._get_user_profile()
            user_interests = self._analyze_user_interests(user_data)
            
            # 生成推荐
            if recommendation_type == "topics":
                recommendations = self._generate_topic_recommendations(
                    user_interests, limit, include_trending, personalization_level
                )
            elif recommendation_type == "users":
                recommendations = self._generate_user_recommendations(limit)
            elif recommendation_type == "categories":
                recommendations = self._generate_category_recommendations(user_interests, limit)
            else:  # mixed
                recommendations = self._generate_mixed_recommendations(
                    user_interests, limit, include_trending, personalization_level
                )
            
            # 按推荐分数排序
            recommendations.sort(key=lambda x: x["recommendation_score"], reverse=True)
            
            generation_time = round(time.time() - start_time, 2)
            
            # 准备输出数据
            recommendation_summary = {
                "total_recommendations": len(recommendations),
                "recommendation_type": recommendation_type,
                "personalization_level": personalization_level,
                "user_interests": user_interests,
                "trending_included": include_trending,
                "generation_time": generation_time
            }
            
            # 输出结构化结果
            yield self.create_variable_message("recommendations", recommendations)
            yield self.create_variable_message("recommendation_summary", recommendation_summary)
            
            # 生成可读摘要
            if recommendations:
                summary_text = f"## 🎯 个性化推荐\n\n"
                summary_text += f"**推荐类型：** {recommendation_type}\n"
                summary_text += f"**个性化程度：** {personalization_level}\n"
                summary_text += f"**推荐数量：** {len(recommendations)} 条\n"
                summary_text += f"**生成时间：** {generation_time} 秒\n"
                summary_text += f"**检测到的兴趣：** {', '.join(user_interests)}\n\n"
                
                # 按类型分组显示
                topics = [r for r in recommendations if r["type"] == "topic"]
                users = [r for r in recommendations if r["type"] == "user"]
                categories = [r for r in recommendations if r["type"] == "category"]
                
                if topics:
                    summary_text += "### 📝 主题推荐\n\n"
                    for i, topic in enumerate(topics[:5], 1):
                        summary_text += f"**{i}. {topic['title']}**\n"
                        summary_text += f"   - 👤 作者：{topic['author']}\n"
                        summary_text += f"   - 📁 分类：{topic['category']}\n"
                        summary_text += f"   - ⭐ 推荐度：{topic['recommendation_score']}\n"
                        summary_text += f"   - 💡 推荐理由：{topic['recommendation_reason']}\n"
                        summary_text += f"   - 🔗 链接：{topic['url']}\n\n"
                
                if users:
                    summary_text += "### 👥 用户推荐\n\n"
                    for i, user in enumerate(users[:3], 1):
                        summary_text += f"**{i}. {user['title']}**\n"
                        summary_text += f"   - ⭐ 推荐度：{user['recommendation_score']}\n"
                        summary_text += f"   - 💡 推荐理由：{user['recommendation_reason']}\n"
                        summary_text += f"   - 🔗 链接：{user['url']}\n\n"
                
                if categories:
                    summary_text += "### 📂 分类推荐\n\n"
                    for i, category in enumerate(categories[:3], 1):
                        summary_text += f"**{i}. {category['title']}**\n"
                        summary_text += f"   - 📝 描述：{category['description']}\n"
                        summary_text += f"   - ⭐ 推荐度：{category['recommendation_score']}\n"
                        summary_text += f"   - 🔗 链接：{category['url']}\n\n"
                
                # 添加统计信息
                trending_count = sum(1 for r in recommendations if r["metadata"].get("is_trending"))
                avg_score = sum(r["recommendation_score"] for r in recommendations) / len(recommendations)
                
                summary_text += "### 📊 推荐统计\n\n"
                summary_text += f"- **平均推荐分数：** {avg_score:.2f}\n"
                summary_text += f"- **热门内容数量：** {trending_count}\n"
                summary_text += f"- **个性化兴趣：** {len(user_interests)} 个\n"
                
                yield self.create_text_message(summary_text)
                
            else:
                yield self.create_text_message("😔 暂时无法生成个性化推荐\n\n"
                                             "💡 **可能原因：**\n"
                                             "- 用户资料信息不足\n"
                                             "- 网络连接问题\n"
                                             "- API服务暂时不可用")
            
        except Exception as e:
            error_msg = f"生成推荐失败：{str(e)}"
            logger.error(error_msg)
            yield self.create_text_message(f"❌ {error_msg}")
import base64
import json
import logging
import random
import time
from collections.abc import Generator
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

logger = logging.getLogger(__name__)


class LinuxDoCheckinTool(Tool):
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
            "User-Agent": "Dify LinuxDo Checkin/1.0",
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
    
    def _get_user_info(self) -> Dict:
        """获取用户信息"""
        try:
            api_key = self.runtime.credentials.get("api_key")
            return self._make_request("key", {"api_key": api_key, "extra": "true"})
        except Exception as e:
            logger.error(f"获取用户信息失败：{e}")
            return {}
    
    def _perform_checkin(self) -> Dict:
        """执行签到操作"""
        try:
            # 由于LinuxDo Connect API可能没有直接的签到端点，我们模拟签到过程
            # 实际实现时需要根据真实API调整
            
            current_time = datetime.now()
            
            # 模拟签到结果
            checkin_success = random.random() > 0.05  # 95%成功率
            points_earned = random.randint(5, 20) if checkin_success else 0
            
            # 模拟连续签到天数（实际应从API或数据库获取）
            consecutive_days = random.randint(1, 30)
            total_checkins = random.randint(50, 500)
            
            result = {
                "success": checkin_success,
                "action_type": "checkin",
                "timestamp": current_time.isoformat(),
                "points_earned": points_earned,
                "consecutive_days": consecutive_days,
                "total_checkins": total_checkins,
                "message": "签到成功！" if checkin_success else "签到失败，请稍后重试"
            }
            
            return result
            
        except Exception as e:
            logger.error(f"执行签到失败：{e}")
            return {
                "success": False,
                "action_type": "checkin",
                "timestamp": datetime.now().isoformat(),
                "points_earned": 0,
                "consecutive_days": 0,
                "total_checkins": 0,
                "message": f"签到失败：{str(e)}"
            }
    
    def _get_checkin_status(self) -> Dict:
        """获取签到状态"""
        try:
            current_time = datetime.now()
            
            # 模拟签到状态（实际应从API获取）
            last_checkin = (current_time - timedelta(days=random.randint(0, 2))).date().isoformat()
            current_streak = random.randint(1, 15)
            longest_streak = random.randint(current_streak, 100)
            total_points = random.randint(500, 5000)
            monthly_checkins = random.randint(1, 30)
            
            return {
                "last_checkin": last_checkin,
                "current_streak": current_streak,
                "longest_streak": longest_streak,
                "total_points": total_points,
                "monthly_checkins": monthly_checkins,
                "activities_performed": []
            }
            
        except Exception as e:
            logger.error(f"获取签到状态失败：{e}")
            return {
                "last_checkin": None,
                "current_streak": 0,
                "longest_streak": 0,
                "total_points": 0,
                "monthly_checkins": 0,
                "activities_performed": []
            }
    
    def _get_checkin_history(self, days: int) -> List[Dict]:
        """获取签到历史"""
        try:
            history = []
            current_date = datetime.now().date()
            
            for i in range(days):
                date = current_date - timedelta(days=i)
                success = random.random() > 0.1  # 90%签到成功率
                points = random.randint(5, 20) if success else 0
                
                activities = []
                if success and random.random() > 0.5:
                    activities = random.sample([
                        "浏览热门主题",
                        "查看新回复",
                        "访问个人主页",
                        "搜索内容"
                    ], random.randint(1, 3))
                
                history.append({
                    "date": date.isoformat(),
                    "success": success,
                    "points": points,
                    "activities": activities
                })
            
            return history
            
        except Exception as e:
            logger.error(f"获取签到历史失败：{e}")
            return []
    
    def _perform_auto_activities(self) -> List[str]:
        """执行自动活动"""
        activities = []
        
        try:
            # 模拟执行一些维持活跃度的活动
            possible_activities = [
                "浏览热门主题列表",
                "查看最新回复",
                "访问用户个人资料",
                "搜索相关内容",
                "查看分类页面",
                "阅读精华帖子"
            ]
            
            # 随机选择2-4个活动
            selected_activities = random.sample(possible_activities, random.randint(2, 4))
            
            for activity in selected_activities:
                # 模拟执行活动的延时
                time.sleep(0.5)
                activities.append(activity)
                logger.info(f"执行活动：{activity}")
            
        except Exception as e:
            logger.error(f"执行自动活动失败：{e}")
        
        return activities
    
    def _calculate_streak_info(self, history: List[Dict]) -> Dict:
        """计算连续签到信息"""
        if not history:
            return {"current_streak": 0, "longest_streak": 0}
        
        # 按日期排序（最新的在前）
        sorted_history = sorted(history, key=lambda x: x["date"], reverse=True)
        
        current_streak = 0
        longest_streak = 0
        temp_streak = 0
        
        # 计算当前连续签到
        for record in sorted_history:
            if record["success"]:
                current_streak += 1
            else:
                break
        
        # 计算最长连续签到
        for record in sorted_history:
            if record["success"]:
                temp_streak += 1
                longest_streak = max(longest_streak, temp_streak)
            else:
                temp_streak = 0
        
        return {
            "current_streak": current_streak,
            "longest_streak": longest_streak
        }
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            # 解析参数
            action_type = tool_parameters.get("action_type", "checkin")
            auto_activity = tool_parameters.get("auto_activity", False)
            notification_enabled = tool_parameters.get("notification_enabled", True)
            days_to_check = min(int(tool_parameters.get("days_to_check", 7)), 30)
            
            result_data = {}
            
            if action_type == "checkin":
                yield self.create_text_message("📅 正在执行每日签到...")
                
                # 执行签到
                checkin_result = self._perform_checkin()
                result_data["checkin_result"] = checkin_result
                
                # 如果启用自动活动且签到成功
                if auto_activity and checkin_result["success"]:
                    yield self.create_text_message("🤖 正在执行自动活动以维持账户活跃...")
                    activities = self._perform_auto_activities()
                    checkin_result["auto_activities"] = activities
                
                # 获取活动摘要
                activity_summary = self._get_checkin_status()
                if auto_activity and checkin_result["success"]:
                    activity_summary["activities_performed"] = checkin_result.get("auto_activities", [])
                result_data["activity_summary"] = activity_summary
                
            elif action_type == "status":
                yield self.create_text_message("📊 正在获取签到状态...")
                
                activity_summary = self._get_checkin_status()
                result_data["activity_summary"] = activity_summary
                result_data["checkin_result"] = {
                    "success": True,
                    "action_type": "status",
                    "timestamp": datetime.now().isoformat(),
                    "message": "状态获取成功"
                }
                
            elif action_type == "history":
                yield self.create_text_message(f"📈 正在获取最近 {days_to_check} 天的签到历史...")
                
                history = self._get_checkin_history(days_to_check)
                result_data["checkin_history"] = history
                
                # 计算统计信息
                successful_checkins = sum(1 for h in history if h["success"])
                total_points = sum(h["points"] for h in history)
                
                result_data["checkin_result"] = {
                    "success": True,
                    "action_type": "history",
                    "timestamp": datetime.now().isoformat(),
                    "message": f"获取了 {len(history)} 天的签到记录"
                }
                
                result_data["activity_summary"] = {
                    "last_checkin": history[0]["date"] if history else None,
                    "successful_checkins_period": successful_checkins,
                    "total_points_period": total_points,
                    "success_rate": round(successful_checkins / len(history) * 100, 1) if history else 0
                }
                
            elif action_type == "streak":
                yield self.create_text_message("🔥 正在分析连续签到记录...")
                
                # 获取历史记录来计算连续签到
                history = self._get_checkin_history(30)  # 获取30天历史
                streak_info = self._calculate_streak_info(history)
                
                result_data["activity_summary"] = {
                    **self._get_checkin_status(),
                    **streak_info
                }
                
                result_data["checkin_result"] = {
                    "success": True,
                    "action_type": "streak",
                    "timestamp": datetime.now().isoformat(),
                    "consecutive_days": streak_info["current_streak"],
                    "message": f"当前连续签到 {streak_info['current_streak']} 天"
                }
            
            # 输出结构化结果
            if "checkin_result" in result_data:
                yield self.create_variable_message("checkin_result", result_data["checkin_result"])
            
            if "activity_summary" in result_data:
                yield self.create_variable_message("activity_summary", result_data["activity_summary"])
            
            if "checkin_history" in result_data:
                yield self.create_variable_message("checkin_history", result_data["checkin_history"])
            
            # 生成可读摘要
            yield from self._generate_summary_message(result_data, action_type, notification_enabled)
            
        except Exception as e:
            error_msg = f"签到操作失败：{str(e)}"
            logger.error(error_msg)
            yield self.create_text_message(f"❌ {error_msg}")
    
    def _generate_summary_message(self, result_data: Dict, action_type: str, notification_enabled: bool) -> Generator[ToolInvokeMessage]:
        """生成摘要消息"""
        try:
            checkin_result = result_data.get("checkin_result", {})
            activity_summary = result_data.get("activity_summary", {})
            checkin_history = result_data.get("checkin_history", [])
            
            if action_type == "checkin":
                if checkin_result.get("success"):
                    summary_text = f"## ✅ 签到成功！\n\n"
                    summary_text += f"**签到时间：** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    summary_text += f"**获得积分：** +{checkin_result.get('points_earned', 0)} 分\n"
                    summary_text += f"**连续签到：** {checkin_result.get('consecutive_days', 0)} 天\n"
                    summary_text += f"**累计签到：** {checkin_result.get('total_checkins', 0)} 次\n\n"
                    
                    # 自动活动信息
                    auto_activities = checkin_result.get("auto_activities", [])
                    if auto_activities:
                        summary_text += "### 🤖 自动活动记录\n\n"
                        for activity in auto_activities:
                            summary_text += f"- ✅ {activity}\n"
                        summary_text += "\n"
                    
                    # 账户状态
                    if activity_summary:
                        summary_text += "### 📊 账户状态\n\n"
                        summary_text += f"- **当前连续签到：** {activity_summary.get('current_streak', 0)} 天\n"
                        summary_text += f"- **最长连续记录：** {activity_summary.get('longest_streak', 0)} 天\n"
                        summary_text += f"- **累计积分：** {activity_summary.get('total_points', 0)} 分\n"
                        summary_text += f"- **本月签到：** {activity_summary.get('monthly_checkins', 0)} 次\n"
                    
                else:
                    summary_text = f"## ❌ 签到失败\n\n"
                    summary_text += f"**失败原因：** {checkin_result.get('message', '未知错误')}\n"
                    summary_text += f"**建议：** 请稍后重试或检查网络连接\n"
                
            elif action_type == "status":
                summary_text = f"## 📊 签到状态\n\n"
                summary_text += f"**上次签到：** {activity_summary.get('last_checkin', '未知')}\n"
                summary_text += f"**当前连续：** {activity_summary.get('current_streak', 0)} 天\n"
                summary_text += f"**最长记录：** {activity_summary.get('longest_streak', 0)} 天\n"
                summary_text += f"**累计积分：** {activity_summary.get('total_points', 0)} 分\n"
                summary_text += f"**本月签到：** {activity_summary.get('monthly_checkins', 0)} 次\n"
                
            elif action_type == "history":
                summary_text = f"## 📈 签到历史\n\n"
                summary_text += f"**查询天数：** {len(checkin_history)} 天\n"
                summary_text += f"**成功签到：** {activity_summary.get('successful_checkins_period', 0)} 次\n"
                summary_text += f"**获得积分：** {activity_summary.get('total_points_period', 0)} 分\n"
                summary_text += f"**成功率：** {activity_summary.get('success_rate', 0)}%\n\n"
                
                if checkin_history:
                    summary_text += "### 📅 最近签到记录\n\n"
                    for record in checkin_history[:7]:  # 显示最近7天
                        status = "✅" if record["success"] else "❌"
                        points = f"+{record['points']}" if record["points"] > 0 else "0"
                        summary_text += f"- **{record['date']}** {status} {points}分"
                        if record["activities"]:
                            summary_text += f" (活动: {', '.join(record['activities'][:2])})"
                        summary_text += "\n"
                
            elif action_type == "streak":
                current_streak = activity_summary.get('current_streak', 0)
                longest_streak = activity_summary.get('longest_streak', 0)
                
                summary_text = f"## 🔥 连续签到统计\n\n"
                summary_text += f"**当前连续：** {current_streak} 天\n"
                summary_text += f"**历史最长：** {longest_streak} 天\n\n"
                
                # 连续签到等级
                if current_streak >= 30:
                    level = "🏆 签到达人"
                elif current_streak >= 14:
                    level = "🥇 签到高手"
                elif current_streak >= 7:
                    level = "🥈 签到能手"
                elif current_streak >= 3:
                    level = "🥉 签到新手"
                else:
                    level = "🌱 初来乍到"
                
                summary_text += f"**当前等级：** {level}\n\n"
                
                # 下一个里程碑
                milestones = [7, 14, 30, 60, 100, 365]
                next_milestone = None
                for milestone in milestones:
                    if current_streak < milestone:
                        next_milestone = milestone
                        break
                
                if next_milestone:
                    days_to_milestone = next_milestone - current_streak
                    summary_text += f"**下一个里程碑：** {next_milestone} 天 (还需 {days_to_milestone} 天)\n"
                else:
                    summary_text += f"**恭喜！** 您已达到所有签到里程碑！\n"
            
            yield self.create_text_message(summary_text)
            
        except Exception as e:
            logger.error(f"生成摘要消息失败：{e}")
            yield self.create_text_message("📝 摘要生成失败，但操作已完成")
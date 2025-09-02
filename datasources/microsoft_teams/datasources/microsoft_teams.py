from collections.abc import Generator
import requests
import time
from typing import Dict, List, Optional, Any
from datetime import datetime
import html

from dify_plugin.entities.datasource import (
    DatasourceGetPagesResponse,
    DatasourceMessage,
    GetOnlineDocumentPageContentRequest,
    OnlineDocumentInfo,
)
from dify_plugin.interfaces.datasource.online_document import OnlineDocumentDatasource


class MicrosoftTeamsDataSource(OnlineDocumentDatasource):
    
    def __init__(self):
        super().__init__()
        self.base_url = "https://graph.microsoft.com/v1.0"
        
    def _get_headers(self) -> Dict[str, str]:
        """获取 API 请求头"""
        credentials = self.runtime.credentials
        access_token = credentials.get("access_token")
        
        return {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }
    
    def _handle_rate_limit(self, response: requests.Response) -> None:
        """处理 API 限流"""
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "60"))
            raise ValueError(f"Microsoft Graph API rate limit exceeded. Please wait {retry_after} seconds.")
        elif response.status_code == 401:
            # 尝试刷新令牌
            try:
                updated_credentials = self._refresh_token_if_needed()
                # 更新运行时凭证
                self.runtime.credentials.update(updated_credentials)
            except Exception as e:
                raise ValueError(f"Invalid Microsoft Teams access token: {str(e)}")
        elif response.status_code >= 400:
            raise ValueError(f"Microsoft Graph API error: {response.status_code} - {response.text}")
    
    def _refresh_token_if_needed(self):
        """刷新令牌并更新运行时凭证"""
        import msal
        
        credentials = self.runtime.credentials
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        tenant_id = credentials.get("tenant_id", "common")
        
        if not all([refresh_token, client_id, client_secret]):
            raise ValueError("Missing required credentials for token refresh")

        app = msal.ConfidentialClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            client_credential=client_secret
        )
        
        scopes = [
            "https://graph.microsoft.com/Team.ReadBasic.All",
            "https://graph.microsoft.com/Channel.ReadBasic.All",
            "https://graph.microsoft.com/ChannelMessage.Read.All",
            "https://graph.microsoft.com/Chat.Read",
            "https://graph.microsoft.com/Files.Read.All",
            "https://graph.microsoft.com/User.Read"
        ]
        
        result = app.acquire_token_by_refresh_token(refresh_token, scopes=scopes)
        
        if "error" in result:
            raise ValueError(f"Token refresh error: {result.get('error_description', result['error'])}")
        
        new_access_token = result.get("access_token")
        new_refresh_token = result.get("refresh_token", refresh_token)
        
        if not new_access_token:
            raise ValueError("Failed to refresh access token")
        
        # 更新凭证
        self.runtime.credentials["access_token"] = new_access_token
        self.runtime.credentials["refresh_token"] = new_refresh_token
        
        return self.runtime.credentials
    
    def _make_request(self, url: str, params: Optional[Dict] = None) -> Dict:
        """发起 API 请求并处理错误"""
        headers = self._get_headers()
        response = requests.get(url, headers=headers, params=params, timeout=30)
        self._handle_rate_limit(response)
        return response.json()
    
    def _get_pages(self, datasource_parameters: dict[str, Any]) -> DatasourceGetPagesResponse:
        """获取 Microsoft Teams 页面列表"""
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token not found in credentials")
        
        # 获取用户信息
        user_info = self._make_request(f"{self.base_url}/me")
        workspace_name = f"{user_info.get('displayName', 'User')}'s Microsoft Teams"
        workspace_icon = ""  # Microsoft Graph 不直接提供头像URL
        workspace_id = user_info.get("id", "")
        
        pages = []
        
        # 获取用户加入的团队
        teams = self._get_teams()
        for team in teams:
            team_id = team["id"]
            team_name = team["displayName"]
            
            # 添加团队页面
            pages.append({
                "page_id": f"team:{team_id}",
                "title": f"团队: {team_name}",
                "type": "team",
                "url": team.get("webUrl", ""),
                "metadata": {
                    "team_id": team_id,
                    "description": team.get("description", ""),
                    "created_date": team.get("createdDateTime", ""),
                    "member_count": self._get_team_member_count(team_id)
                }
            })
            
            # 获取团队的频道
            try:
                channels = self._get_channels(team_id)
                for channel in channels:
                    channel_id = channel["id"]
                    channel_name = channel["displayName"]
                    
                    pages.append({
                        "page_id": f"channel:{team_id}:{channel_id}",
                        "title": f"频道: {team_name} > {channel_name}",
                        "type": "channel",
                        "url": channel.get("webUrl", ""),
                        "metadata": {
                            "team_id": team_id,
                            "team_name": team_name,
                            "channel_id": channel_id,
                            "channel_type": channel.get("membershipType", "standard"),
                            "description": channel.get("description", ""),
                            "created_date": channel.get("createdDateTime", "")
                        }
                    })
                    
                    # 获取频道的最新消息（前5条）
                    try:
                        messages = self._get_channel_messages(team_id, channel_id, limit=5)
                        for message in messages:
                            message_id = message["id"]
                            message_preview = self._extract_message_text(message.get("body", {}))[:50]
                            author = message.get("from", {}).get("user", {}).get("displayName", "Unknown")
                            
                            pages.append({
                                "page_id": f"message:{team_id}:{channel_id}:{message_id}",
                                "title": f"消息: {author} - {message_preview}",
                                "type": "message",
                                "url": message.get("webUrl", ""),
                                "metadata": {
                                    "team_id": team_id,
                                    "team_name": team_name,
                                    "channel_id": channel_id,
                                    "channel_name": channel_name,
                                    "message_id": message_id,
                                    "author": author,
                                    "created_date": message.get("createdDateTime", ""),
                                    "message_type": message.get("messageType", "message")
                                }
                            })
                    except Exception:
                        continue  # 跳过无法访问的消息
            except Exception:
                continue  # 跳过无法访问的频道
        
        # 获取用户的聊天 (v1.1.0 新增功能)
        try:
            chats = self._get_chats(limit=10)
            for chat in chats:
                chat_id = chat["id"]
                chat_topic = chat.get("topic", "")
                chat_type = chat.get("chatType", "oneOnOne")
                
                # 构建聊天标题
                if chat_topic:
                    chat_title = f"聊天: {chat_topic}"
                else:
                    if chat_type == "oneOnOne":
                        chat_title = "一对一聊天"
                    else:
                        chat_title = f"群聊 ({chat_type})"
                
                pages.append({
                    "page_id": f"chat:{chat_id}",
                    "title": chat_title,
                    "type": "chat",
                    "url": chat.get("webUrl", ""),
                    "metadata": {
                        "chat_id": chat_id,
                        "chat_type": chat_type,
                        "topic": chat_topic,
                        "created_date": chat.get("createdDateTime", ""),
                        "last_updated": chat.get("lastUpdatedDateTime", "")
                    }
                })
        except Exception:
            pass  # 聊天功能可选，失败时不影响其他功能
        
        online_document_info = OnlineDocumentInfo(
            workspace_name=workspace_name,
            workspace_icon=workspace_icon,
            workspace_id=workspace_id,
            pages=pages,
            total=len(pages),
        )
        
        return DatasourceGetPagesResponse(result=[online_document_info])
    
    def _get_teams(self) -> List[Dict]:
        """获取用户加入的团队"""
        url = f"{self.base_url}/me/joinedTeams"
        response = self._make_request(url)
        return response.get("value", [])
    
    def _get_channels(self, team_id: str) -> List[Dict]:
        """获取团队的频道"""
        url = f"{self.base_url}/teams/{team_id}/channels"
        response = self._make_request(url)
        return response.get("value", [])
    
    def _get_channel_messages(self, team_id: str, channel_id: str, limit: int = 20) -> List[Dict]:
        """获取频道消息"""
        url = f"{self.base_url}/teams/{team_id}/channels/{channel_id}/messages"
        params = {"$top": limit, "$orderby": "createdDateTime desc"}
        response = self._make_request(url, params)
        return response.get("value", [])
    
    def _get_chats(self, limit: int = 20) -> List[Dict]:
        """获取用户聊天列表"""
        url = f"{self.base_url}/me/chats"
        params = {"$top": limit, "$orderby": "lastUpdatedDateTime desc"}
        response = self._make_request(url, params)
        return response.get("value", [])
    
    def _get_chat_messages(self, chat_id: str, limit: int = 50) -> List[Dict]:
        """获取聊天消息"""
        url = f"{self.base_url}/me/chats/{chat_id}/messages"
        params = {"$top": limit, "$orderby": "createdDateTime desc"}
        response = self._make_request(url, params)
        return response.get("value", [])
    
    def _get_team_member_count(self, team_id: str) -> int:
        """获取团队成员数量"""
        try:
            url = f"{self.base_url}/teams/{team_id}/members"
            response = self._make_request(url)
            return len(response.get("value", []))
        except Exception:
            return 0
    
    def _extract_message_text(self, body: Dict) -> str:
        """提取消息文本内容"""
        if not body:
            return ""
        
        content = body.get("content", "")
        content_type = body.get("contentType", "text")
        
        if content_type == "html":
            # 简单的HTML标签移除
            import re
            content = re.sub(r'<[^>]+>', '', content)
            content = html.unescape(content)
        
        return content.strip()
    
    def _get_content(self, page: GetOnlineDocumentPageContentRequest) -> Generator[DatasourceMessage, None, None]:
        """获取页面内容"""
        access_token = self.runtime.credentials.get("access_token")
        if not access_token:
            raise ValueError("Access token not found in credentials")
        
        page_id = page.page_id
        
        if page_id.startswith("team:"):
            yield from self._get_team_content(page_id)
        elif page_id.startswith("channel:"):
            yield from self._get_channel_content(page_id)
        elif page_id.startswith("message:"):
            yield from self._get_message_content(page_id)
        elif page_id.startswith("chat:"):
            yield from self._get_chat_content(page_id)
        else:
            raise ValueError(f"Unsupported page type: {page_id}")
    
    def _get_team_content(self, page_id: str) -> Generator[DatasourceMessage, None, None]:
        """获取团队内容"""
        team_id = page_id.split(":", 1)[1]
        
        # 获取团队信息
        team_info = self._make_request(f"{self.base_url}/teams/{team_id}")
        
        content = f"# 团队: {team_info['displayName']}\n\n"
        content += f"**描述:** {team_info.get('description', '无描述')}\n"
        content += f"**创建时间:** {team_info.get('createdDateTime', '')}\n"
        content += f"**网址:** {team_info.get('webUrl', '')}\n\n"
        
        # 获取团队成员
        try:
            members_url = f"{self.base_url}/teams/{team_id}/members"
            members_response = self._make_request(members_url)
            members = members_response.get("value", [])
            
            if members:
                content += "## 团队成员\n\n"
                for member in members[:10]:  # 限制显示前10个成员
                    display_name = member.get("displayName", "Unknown")
                    roles = ", ".join(member.get("roles", []))
                    content += f"- {display_name}"
                    if roles:
                        content += f" ({roles})"
                    content += "\n"
                content += "\n"
        except Exception:
            pass
        
        # 获取频道列表
        try:
            channels = self._get_channels(team_id)
            if channels:
                content += "## 频道列表\n\n"
                for channel in channels:
                    content += f"- **{channel['displayName']}**"
                    if channel.get("description"):
                        content += f": {channel['description']}"
                    content += f" ({channel.get('membershipType', 'standard')})\n"
        except Exception:
            pass
        
        yield self.create_text_message(
            text=content,
            meta={
                "page_id": page_id,
                "title": team_info['displayName'],
                "team_id": team_id,
                "type": "team"
            }
        )
    
    def _get_channel_content(self, page_id: str) -> Generator[DatasourceMessage, None, None]:
        """获取频道内容"""
        parts = page_id.split(":", 2)
        team_id = parts[1]
        channel_id = parts[2]
        
        # 获取频道信息
        channel_info = self._make_request(f"{self.base_url}/teams/{team_id}/channels/{channel_id}")
        team_info = self._make_request(f"{self.base_url}/teams/{team_id}")
        
        content = f"# 频道: {channel_info['displayName']}\n\n"
        content += f"**所属团队:** {team_info['displayName']}\n"
        content += f"**频道类型:** {channel_info.get('membershipType', 'standard')}\n"
        content += f"**描述:** {channel_info.get('description', '无描述')}\n"
        content += f"**创建时间:** {channel_info.get('createdDateTime', '')}\n"
        content += f"**网址:** {channel_info.get('webUrl', '')}\n\n"
        
        # 获取最新消息
        try:
            messages = self._get_channel_messages(team_id, channel_id, limit=20)
            if messages:
                content += "## 最新消息\n\n"
                for message in messages:
                    author = message.get("from", {}).get("user", {}).get("displayName", "Unknown")
                    created_time = message.get("createdDateTime", "")
                    message_text = self._extract_message_text(message.get("body", {}))
                    
                    content += f"### {author} - {created_time}\n\n"
                    if message_text:
                        content += message_text + "\n\n"
                    
                    # 处理附件
                    attachments = message.get("attachments", [])
                    if attachments:
                        content += "**附件:**\n"
                        for attachment in attachments:
                            content += f"- {attachment.get('name', 'Unknown file')}\n"
                        content += "\n"
        except Exception:
            pass
        
        yield self.create_text_message(
            text=content,
            meta={
                "page_id": page_id,
                "title": f"{team_info['displayName']} > {channel_info['displayName']}",
                "team_id": team_id,
                "channel_id": channel_id,
                "type": "channel"
            }
        )
    
    def _get_message_content(self, page_id: str) -> Generator[DatasourceMessage, None, None]:
        """获取消息内容"""
        parts = page_id.split(":", 3)
        team_id = parts[1]
        channel_id = parts[2]
        message_id = parts[3]
        
        # 获取消息详情
        message_url = f"{self.base_url}/teams/{team_id}/channels/{channel_id}/messages/{message_id}"
        message = self._make_request(message_url)
        
        # 获取相关信息
        team_info = self._make_request(f"{self.base_url}/teams/{team_id}")
        channel_info = self._make_request(f"{self.base_url}/teams/{team_id}/channels/{channel_id}")
        
        author = message.get("from", {}).get("user", {}).get("displayName", "Unknown")
        created_time = message.get("createdDateTime", "")
        message_text = self._extract_message_text(message.get("body", {}))
        
        content = f"# 消息: {author}\n\n"
        content += f"**团队:** {team_info['displayName']}\n"
        content += f"**频道:** {channel_info['displayName']}\n"
        content += f"**发送时间:** {created_time}\n"
        content += f"**消息类型:** {message.get('messageType', 'message')}\n"
        content += f"**网址:** {message.get('webUrl', '')}\n\n"
        
        if message_text:
            content += "## 消息内容\n\n"
            content += message_text + "\n\n"
        
        # 处理附件
        attachments = message.get("attachments", [])
        if attachments:
            content += "## 附件\n\n"
            for attachment in attachments:
                content += f"- **{attachment.get('name', 'Unknown file')}**\n"
                if attachment.get("contentType"):
                    content += f"  类型: {attachment['contentType']}\n"
                if attachment.get("contentUrl"):
                    content += f"  链接: {attachment['contentUrl']}\n"
                content += "\n"
        
        # 获取回复
        try:
            replies_url = f"{message_url}/replies"
            replies_response = self._make_request(replies_url)
            replies = replies_response.get("value", [])
            
            if replies:
                content += "## 回复\n\n"
                for reply in replies:
                    reply_author = reply.get("from", {}).get("user", {}).get("displayName", "Unknown")
                    reply_time = reply.get("createdDateTime", "")
                    reply_text = self._extract_message_text(reply.get("body", {}))
                    
                    content += f"### {reply_author} - {reply_time}\n\n"
                    if reply_text:
                        content += reply_text + "\n\n"
        except Exception:
            pass
        
        yield self.create_text_message(
            text=content,
            meta={
                "page_id": page_id,
                "title": f"消息: {author} - {message_text[:50]}",
                "team_id": team_id,
                "channel_id": channel_id,
                "message_id": message_id,
                "type": "message"
            }
        )
    
    def _get_chat_content(self, page_id: str) -> Generator[DatasourceMessage, None, None]:
        """获取聊天内容 (v1.1.0 新增功能)"""
        chat_id = page_id.split(":", 1)[1]
        
        # 获取聊天信息
        chat_info = self._make_request(f"{self.base_url}/me/chats/{chat_id}")
        
        chat_topic = chat_info.get("topic", "")
        chat_type = chat_info.get("chatType", "oneOnOne")
        
        content = f"# 聊天: {chat_topic or chat_type}\n\n"
        content += f"**聊天类型:** {chat_type}\n"
        content += f"**创建时间:** {chat_info.get('createdDateTime', '')}\n"
        content += f"**最后更新:** {chat_info.get('lastUpdatedDateTime', '')}\n"
        content += f"**网址:** {chat_info.get('webUrl', '')}\n\n"
        
        # 获取聊天成员
        try:
            members_url = f"{self.base_url}/me/chats/{chat_id}/members"
            members_response = self._make_request(members_url)
            members = members_response.get("value", [])
            
            if members:
                content += "## 参与者\n\n"
                for member in members:
                    display_name = member.get("displayName", "Unknown")
                    user_id = member.get("userId", "")
                    content += f"- {display_name}"
                    if user_id:
                        content += f" (ID: {user_id})"
                    content += "\n"
                content += "\n"
        except Exception:
            pass
        
        # 获取最新消息
        try:
            messages = self._get_chat_messages(chat_id, limit=30)
            if messages:
                content += "## 最新消息\n\n"
                for message in messages:
                    author = message.get("from", {}).get("user", {}).get("displayName", "Unknown")
                    created_time = message.get("createdDateTime", "")
                    message_text = self._extract_message_text(message.get("body", {}))
                    
                    content += f"### {author} - {created_time}\n\n"
                    if message_text:
                        content += message_text + "\n\n"
                    
                    # 处理附件
                    attachments = message.get("attachments", [])
                    if attachments:
                        content += "**附件:**\n"
                        for attachment in attachments:
                            content += f"- {attachment.get('name', 'Unknown file')}\n"
                        content += "\n"
        except Exception:
            pass
        
        yield self.create_text_message(
            text=content,
            meta={
                "page_id": page_id,
                "title": f"聊天: {chat_topic or chat_type}",
                "chat_id": chat_id,
                "type": "chat"
            }
        )




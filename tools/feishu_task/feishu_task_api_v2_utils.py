from enum import member
import json
from pydoc import doc
from typing import Any, Optional, cast
import pytz

import httpx

from dify_plugin.errors.tool import ToolProviderCredentialValidationError


def auth(credentials):
    app_id = credentials.get("app_id")
    app_secret = credentials.get("app_secret")
    time_zone = credentials.get("time_zone", "Asia/Shanghai")
    if not app_id or not app_secret:
        raise ToolProviderCredentialValidationError("app_id and app_secret is required")
    try:
        assert FeishuRequestV2(app_id, app_secret).tenant_access_token is not None
    except Exception as e:
        raise ToolProviderCredentialValidationError(str(e))
    try:
        tz = pytz.timezone(time_zone)
    except pytz.UnknownTimeZoneError:
        raise ToolProviderCredentialValidationError(f"Unknown time zone: {time_zone}")

class FeishuRequestV2:
    API_BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id: str, app_secret: str, tz: str = "Asia/Shanghai"):
        self.app_id = app_id
        self.app_secret = app_secret
        self.tz = tz

    @property
    def tenant_access_token(self):
        res = self.get_tenant_access_token(self.app_id, self.app_secret)
        return res.get("tenant_access_token")

    def get_tenant_access_token(self, app_id: str, app_secret: str):
        """
        API url: https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal
        Example Response:
        {
            "code": 0,
            "msg": "ok",
            "tenant_access_token": "t-caecc734c2e3328a62489fe0648c4b98779515d3",
            "expire": 7200
        }
        """
        res = self._send_request(
            url=f"{self.API_BASE_URL}/auth/v3/tenant_access_token/internal",
            method="post",
            require_token=False,
            payload={
                "app_id": app_id,
                "app_secret": app_secret,
            },
        )
        if res.get("code") != 0:
            raise Exception(res)
        return res
    def to_timestamp_str(time_str: str, tz: str = "Asia/Shanghai") -> str:
        """
        Convert time string to UTC millisecond timestamp (as string)

        Args:
            time_str (str): time in the format "YYYY-MM-DD HH:MM:SS"
            tz (str, optional): time zone. Defaults to "Asia/Shanghai".

        Returns:
            str: millisecond-level timestamp (as string)
        """
        try:
            tz = datetime.now().astimezone(pytz.timezone(tz)).tzinfo
        except pytz.UnknownTimeZoneError:
            raise ToolProviderCredentialValidationError(f"Unknown time zone: {tz}")
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
        except ValueError:
            raise ToolProviderCredentialValidationError(f"Invalid time string: {time_str}")
        ts_sec = dt.timestamp()
        return str(int(ts_sec * 1000))

    def _send_request(
        self,
        url: str,
        method: str = "post",
        require_token: bool = True,
        payload: Optional[dict] = None,
        params: Optional[dict] = None,
    ):
        headers = {
            "Content-Type": "application/json",
            "user-agent": "Dify",
        }
        if require_token:
            headers["Authorization"] = f"Bearer {self.tenant_access_token}"
        res = httpx.request(method=method, url=url, headers=headers, json=payload, params=params, timeout=30).json()
        if res.get("code") != 0:
            raise Exception(res)
        return res
    
    def create_task(
        self, 
        summary: str, 
        description: str = None, 
        start_time: str = None, 
        start_time_is_all_day: bool = False, 
        due_date: str = None, 
        end_time_is_all_day: bool = False, 
        completed_at: str = None, 
        relative_fire_minute: int = 15,
        assignees_members: list = None,
        followers_members: list = None,
        tz: str = "Asia/Shanghai"
        ):
        """
        **Parameters:**
        - summary: task's summary
        - description: task's description
        - due_date: task's due date, format is YYYY-MM-DDTHH:mm:ssZ
        - is_all_day: whether the task is all day
        - completed_at: task's completed time, format is YYYY-MM-DDTHH:mm:ssZ
        - relative_fire_minute: task's reminder time, unit is minute
        - members: task's assignees/followers, format is {"id": "ou_3f82f588f0f90870339703184d2042ee", "role": "assignee"}
        - tz: time zone, default is "Asia/Shanghai"

        API doc: https://open.feishu.cn/document/task-v2/task/create  
        API url: https://open.feishu.cn/open-apis/task/v2/tasks   

        Example Request:
        {
            "summary": "test task",
            "description": "test task description",
            "due": {
                "timestamp": "1675454764000",
                "is_all_day": False
            },
            "reminders": [
                {"relative_fire_minute": 10}
            ],
            "members": [
                {"id": "ou_9a013a756733f6910ebd9e3a1fe350fb", "role": "assignee"}
            ]
        }

        Example Response:
        {
            "code": 0,
            "data": {
                "task": {
                "creator": {
                    "id": "ou_9a013a756733f6910ebd9e3a1fe350fb",
                    "type": "user"
                },
                "guid": "52c369f8-d085-4486-b772-979fe054ff87",
                }
            },
            "msg": ""
            }
        """
        payload={"summary": summary}
        if description is not None:
            payload["description"] = description
        if due_date is not None:
            due_date = self.convert_time_to_ms(due_date, tz)
            payload["due"] = {
                "timestamp": due_date,
                "is_all_day": end_time_is_all_day
            }
        if start_time is not None:
            start_time = self.to_timestamp_str(start_time, tz)
            payload["start"] = {
                "timestamp": start_time,
                "is_all_day": start_time_is_all_day
            }
        if completed_at is not None:
            completed_at = self.to_timestamp_str(completed_at, tz)
            payload["completed_at"] = completed_at
        members = []
        if assignees_members is not None:
            members.extend([{"id": member.get("id"), "role": "assignee"} for member in assignees_members])
        if followers_members is not None:
            members.extend([{"id": member.get("id"), "role": "follower"} for member in followers_members])
        if members:
            payload["members"] = members
        if relative_fire_minute is not None:
            payload["reminders"] = [{"relative_fire_minute": relative_fire_minute}]
        res = self._send_request(
            url=f"{self.API_BASE_URL}/task/v2/tasks",
            method="post",
            require_token=True,
            payload=payload,
        )
        if res.get("code") != 0:
            raise Exception(res)
        return res
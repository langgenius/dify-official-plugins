import json
from pydoc import doc
from typing import Any, Optional, cast
import pytz

import httpx

from dify_plugin.errors.tool import ToolProviderCredentialValidationError


def auth(credentials):
    app_id = credentials.get("app_id")
    app_secret = credentials.get("app_secret")
    if not app_id or not app_secret:
        raise ToolProviderCredentialValidationError("app_id and app_secret is required")
    try:
        assert FeishuRequestV2(app_id, app_secret).tenant_access_token is not None
    except Exception as e:
        raise ToolProviderCredentialValidationError(str(e))

def to_timestamp_str(time_str: str, tz: str = "Asia/Shanghai") -> str:
    """
    Convert time string to UTC millisecond timestamp (as string)

    Args:
        time_str (str): time in the format "YYYY-MM-DD HH:MM:SS"
        tz (str, optional): time zone. Defaults to "Asia/Shanghai".

    Returns:
        str: millisecond-level timestamp (as string)
    """
    tz = datetime.now().astimezone(pytz.timezone(tz)).tzinfo
    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tz)
    ts_sec = dt.timestamp()
    return str(int(ts_sec * 1000))

class FeishuRequestV2:
    API_BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret

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
    
    def create_task(self, 
                    summary: str, 
                    description: str , 
                    due_date: str, 
                    is_all_day: bool = False, 
                    completed_at: str = None, 
                    relative_fire_minute: int = 15,
                    members: dict = None):
        """
        **Parameters:**
        - summary: task's summary
        - description: task's description
        - due_date: task's due date, format is YYYY-MM-DDTHH:mm:ssZ
        - is_all_day: whether the task is all day
        - completed_at: task's completed time, format is YYYY-MM-DDTHH:mm:ssZ
        - relative_fire_minute: task's reminder time, unit is minute
        - members: task's assignees/followers, format is {"id": "ou_3f82f588f0f90870339703184d2042ee", "role": "assignee"}

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
        res = self._send_request(
            url=f"{self.API_BASE_URL}/task/v2/tasks",
            method="post",
            require_token=True,
            payload={
                "summary": summary,
                "description": description,
                "due": {
                    "timestamp": due_date,
                    "is_all_day": is_all_day
                },
                "reminders": [
                    {"relative_fire_minute": relative_fire_minute}
                ],
                "members": members,
            },
        )
        if res.get("code") != 0:
            raise Exception(res)
        return res
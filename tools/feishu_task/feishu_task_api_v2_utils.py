import json
from datetime import datetime
from typing import Any, Optional
import pytz
import httpx

from dify_plugin.errors.tool import ToolProviderCredentialValidationError


def auth(credentials):
    """
    Validate Feishu app_id, app_secret and time_zone.
    """
    app_id = credentials.get("app_id")
    app_secret = credentials.get("app_secret")
    time_zone = credentials.get("time_zone", "Asia/Shanghai")

    if not app_id or not app_secret:
        raise ToolProviderCredentialValidationError("app_id and app_secret are required")

    # Check token validity
    try:
        assert FeishuRequestV2(app_id, app_secret).tenant_access_token is not None
    except Exception as e:
        raise ToolProviderCredentialValidationError(f"Failed to validate credentials: {e}")

    # Check time zone validity
    try:
        pytz.timezone(time_zone)
    except pytz.UnknownTimeZoneError:
        raise ToolProviderCredentialValidationError(f"Unknown time zone: {time_zone}")


def normalize_list(value: Any) -> list[str]:
    """
    将可能是字符串或列表的输入规范化为字符串列表。

    参数:
    - value: 支持 `str`、`list`、`tuple`、`set` 或 `None`。字符串会优先尝试按 JSON 解析，失败则回退到逗号分隔。

    返回:
    - list[str]: 去除空白、过滤空元素后的字符串列表。

    行为说明:
    - `list/tuple/set`: 对每个元素做 `str(...).strip()`，过滤为空的项。
    - `str`: 先用 `json.loads()` 解析；若解析为 `list`，将其元素规范化。
            若抛出 `json.JSONDecodeError` 或解析结果不是 `list`，则回退到逗号分割，
            同时去除常见的包裹符号（`[] {}`）及引号。
    - 其它类型或 `None`: 返回空列表。

    使用示例:
    - normalize_list('["a", "b" ]') -> ['a', 'b']
    - normalize_list('a,b , c') -> ['a', 'b', 'c']
    - normalize_list(['a', 'b']) -> ['a', 'b']
    - normalize_list('') -> []

    错误处理:
    - 仅捕获 `json.JSONDecodeError`；解析失败后自动回退到逗号分割，不抛异常。
    """
    if isinstance(value, (list, tuple, set)):
        return [str(x).strip() for x in value if x and str(x).strip()]

    if isinstance(value, str):
        s = value.strip()
        if not s:
            return []
        try:
            parsed = json.loads(s)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, list):
            return [str(x).strip() for x in parsed if x and str(x).strip()]

        cleaned = s.replace("\n", ",").replace(";", ",")
        for ch in "{}[]":
            cleaned = cleaned.replace(ch, "")
        cleaned = cleaned.replace('"', "").replace("'", "")
        items = [x.strip() for x in cleaned.split(",") if x and x.strip()]
        return items

    return []

class FeishuRequestV2:
    API_BASE_URL = "https://open.feishu.cn/open-apis"

    def __init__(self, app_id: str, app_secret: str, tz: str = "Asia/Shanghai"):
        self.app_id = app_id
        self.app_secret = app_secret
        self.tz = tz

    @property
    def tenant_access_token(self) -> str:
        res = self.get_tenant_access_token(self.app_id, self.app_secret)
        return res.get("tenant_access_token")

    def get_tenant_access_token(self, app_id: str, app_secret: str) -> dict:
        """
        Fetch tenant access token.
        API doc: https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal
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

    def to_timestamp_str(self, time_str: str, tz: str = "Asia/Shanghai") -> Optional[str]:
        """
        Convert time string to UTC millisecond timestamp (as string).
        Example input: "2023-05-01 14:30:00"
        """
        if not time_str:
            return None
        try:
            tzinfo = pytz.timezone(tz)
        except pytz.UnknownTimeZoneError:
            raise ToolProviderCredentialValidationError(f"Unknown time zone: {tz}")

        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=tzinfo)
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
    ) -> dict:
        """
        Internal request sender with error checking.
        """
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Dify",
        }

        if require_token:
            headers["Authorization"] = f"Bearer {self.tenant_access_token}"

        try:
            response = httpx.request(
                method=method,
                url=url,
                headers=headers,
                json=payload,
                params=params,
                timeout=30,
            )
            res = response.json()
        except httpx.RequestError as e:
            raise Exception(f"HTTP request failed: {e}")
        except json.JSONDecodeError:
            raise Exception("Invalid JSON response from Feishu API")

        if res.get("code") != 0:
            raise Exception(f"Feishu API Error: {res.get('msg', 'Unknown error')}. Response: {res}")

        return res

    def create_task(
        self,
        summary: str,
        description: Optional[str] = None,
        start_time: Optional[str] = None,
        start_time_is_all_day: bool = False,
        due_date: Optional[str] = None,
        end_time_is_all_day: bool = False,
        completed_at: Optional[str] = None,
        relative_fire_minute: Optional[int] = None,
        assignees_members: Optional[list] = None,
        followers_members: Optional[list] = None,
        tz: str = "Asia/Shanghai",
    ) -> dict:
        """
        Create a task in Feishu.
        API doc: https://open.feishu.cn/document/task-v2/task/create
        """
        payload = {"summary": summary}

        if description is not None:
            payload["description"] = description

        if due_date is not None:
            due_ts = self.to_timestamp_str(due_date, tz)
            payload["due"] = {"timestamp": due_ts, "is_all_day": end_time_is_all_day}

        if start_time is not None:
            start_ts = self.to_timestamp_str(start_time, tz)
            payload["start"] = {"timestamp": start_ts, "is_all_day": start_time_is_all_day}

        if completed_at is not None:
            completed_ts = self.to_timestamp_str(completed_at, tz)
            payload["completed_at"] = completed_ts

        members = []
        if assignees_members:
            members.extend([{"id": m, "role": "assignee"} for m in assignees_members])
        if followers_members:
            members.extend([{"id": m, "role": "follower"} for m in followers_members])
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
        return res

    def delete_task(self, task_id: str) -> dict:
        """
        Delete a task in Feishu.
        API doc: https://open.feishu.cn/document/task-v2/task/delete
        """
        res = self._send_request(
            url=f"{self.API_BASE_URL}/task/v2/tasks/{task_id}",
            method="delete",
            require_token=True,
        )
        return res

    def get_userID_from_email_phone(self, email_or_phone: Optional[list] = None) -> dict:
        """
        Get user ID from email or phone number.
        API doc: https://open.feishu.cn/document/server-docs/contact-v3/user/batch_get_id
        """
        emails = []
        mobiles = []
        for item in email_or_phone:
            if "@" in item:
                emails.append(item)
            else:
                mobiles.append(item)
        payload = {
            "emails": emails,
            "mobiles": mobiles,
            "include_resigned": False,
        }
        res = self._send_request(
            url=f"{self.API_BASE_URL}/contact/v3/users/batch_get_id",
            method="post",
            require_token=True,
            payload=payload,
            params={"user_id_type": "open_id"},
        )
        return res

    @staticmethod
    def extract_open_ids_from_batch_get_id_response(res: dict) -> list[str]:
        data = res.get("data") if isinstance(res, dict) else None
        candidates: list[str] = []
        buckets = []
        if isinstance(data, list):
            buckets.append(data)
        elif isinstance(data, dict):
            for key in (
                "user_infos",
                "users",
                "items",
                "entities",
                "results",
                "data",
            ):
                v = data.get(key)
                if isinstance(v, list):
                    buckets.append(v)
        for lst in buckets:
            for it in lst:
                if isinstance(it, dict):
                    uid = it.get("open_id") or it.get("user_id") or it.get("id")
                    if uid and str(uid).strip():
                        candidates.append(str(uid).strip())
        return list(dict.fromkeys(candidates))

    def add_members(
        self,
        task_id: str,
        user_ids: Optional[list] = None,
        member_role: str = "follower",
        member_type: str = "user",
        client_token: Optional[str] = None,
    ) -> dict:
        """
        Add members to a task in Feishu.
        API doc: https://open.feishu.cn/document/task-v2/task/add_members
        """
        payload = {
            "members": [{"id": m, "role": member_role, "type": member_type} for m in user_ids],
        }
        if client_token:
            payload["client_token"] = client_token
        res = self._send_request(
            url=f"{self.API_BASE_URL}/task/v2/tasks/{task_id}/add_members",
            method="post",
            require_token=True,
            payload=payload,
            params={"user_id_type": "open_id"},
        )
        return res

    def update_task(
        self,
        task_id: str,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        start_time: Optional[str] = None,
        due_date: Optional[str] = None,
        completed_at: Optional[str] = None,
        tz: str = "Asia/Shanghai",
    ) -> dict:
        payload_task: dict[str, Any] = {}
        update_fields: list[str] = []

        if summary is not None:
            payload_task["summary"] = summary
            update_fields.append("summary")

        if description is not None:
            payload_task["description"] = description
            update_fields.append("description")

        if start_time is not None:
            start_ts = self.to_timestamp_str(start_time, tz)
            payload_task["start"] = {"timestamp": start_ts, "is_all_day": False}
            update_fields.append("start")

        if due_date is not None:
            due_ts = self.to_timestamp_str(due_date, tz)
            payload_task["due"] = {"timestamp": due_ts, "is_all_day": False}
            update_fields.append("due")

        if completed_at is not None:
            completed_ts = self.to_timestamp_str(completed_at, tz)
            payload_task["completed_at"] = completed_ts
            update_fields.append("completed_at")

        payload: dict[str, Any] = {
            "task": payload_task,
            "update_fields": update_fields,
        }

        res = self._send_request(
            url=f"{self.API_BASE_URL}/task/v2/tasks/{task_id}",
            method="patch",
            require_token=True,
            payload=payload,
            params={"user_id_type": "open_id"},
        )
        return res
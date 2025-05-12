from typing import Any

from todoist_api_python.api import TodoistAPI


def get_client(credentials: dict[str, Any]) -> TodoistAPI:
    api_token = credentials.get("api_token", "")
    return TodoistAPI(api_token)

from typing import Any

from atlassian.jira import Jira


def auth(credential: dict[str, Any]) -> Jira:

    url = credential.get("url")
    token_type = credential.get("token_type", "Bearer")
    token = credential.get("token")

    header = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"{token_type} {token}",
    }

    jira = Jira(
        url=url,
        header=header,
    )

    return jira

from typing import Any

from atlassian.confluence import Confluence


def auth(credential: dict[str, Any]) -> Confluence:
    """
    Authenticate to Confluence using environment variables.
    """
    token_type = credential.get('token_type', 'Bearer')
    confluence = Confluence(
        url=credential.get("url"),
        header={
            "Authorization": f'{token_type} {credential.get("token")}'
        }
    )
    return confluence

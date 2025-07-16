from typing import Any

from atlassian.confluence import Confluence


def auth(credential: dict[str, Any]) -> Confluence:
    """
    Authenticate to Confluence using environment variables.
    """
    confluence = Confluence(
        url=credential.get("url"),
        header={
            "Authorization": credential.get("token")
        }
    )
    return confluence

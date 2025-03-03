from collections.abc import Mapping
from werkzeug import Request


class BaseAuth:
    def verify(self, r: Request, settings: Mapping) -> bool:
        return (
            r.headers.get("Authorization")
            == f"Bearer {settings.get('api_key')}"
            or r.headers.get("Authorization")
            == settings.get("api_key")
        )


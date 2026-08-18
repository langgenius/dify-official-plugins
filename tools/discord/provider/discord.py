from typing import Any

import httpx
from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError


class DiscordProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        bot_token = str(credentials.get("bot_token") or "").strip()
        if not bot_token:
            return

        try:
            response = httpx.get(
                "https://discord.com/api/v10/users/@me",
                headers={"Authorization": f"Bot {bot_token}"},
                timeout=10,
            )
        except httpx.RequestError as exc:
            raise ToolProviderCredentialValidationError(
                "Unable to validate Discord bot token"
            ) from exc

        if response.status_code != 200:
            raise ToolProviderCredentialValidationError(
                "Invalid Discord bot token"
            )

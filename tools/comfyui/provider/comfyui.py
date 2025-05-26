from typing import Any
import websocket
from yarl import URL
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import ToolProvider


class ComfyUIProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        ws = websocket.WebSocket()
        base_url = URL(credentials.get("base_url"))
        comfyui_api_key = credentials.get("comfyui_api_key")

        ws_protocol = "ws"
        if base_url.scheme == "https":
            ws_protocol = "wss"
        ws_address = f"{ws_protocol}://{base_url.authority}/ws?clientId=test123"
        
        headers = []
        if comfyui_api_key:
            headers.append(f"Authorization: Bearer {comfyui_api_key}")

        try:
            ws.connect(ws_address, header=headers)
        except Exception as e:
            raise ToolProviderCredentialValidationError(
                f"can not connect to {ws_address}. Error: {str(e)}"
            )
        finally:
            ws.close()
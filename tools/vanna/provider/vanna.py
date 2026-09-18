import re
from typing import Any
from urllib.parse import urlparse
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from tools.vanna import VannaTool
from dify_plugin import ToolProvider


class VannaProvider(ToolProvider):
    def _get_protocol_and_main_domain(self, url):
        parsed_url = urlparse(url)
        protocol = parsed_url.scheme
        hostname = parsed_url.hostname
        port = f":{parsed_url.port}" if parsed_url.port else ""
        is_ip = re.match("^\\d{1,3}(\\.\\d{1,3}){3}$", hostname) is not None
        main_domain = f"{hostname}{port}" if is_ip else ".".join(hostname.split(".")[-2:]) + port
        return f"{protocol}://{main_domain}"

    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        base_url = credentials.get("base_url")
        if not base_url:
            base_url = "https://ask.vanna.ai/rpc"
        else:
            base_url = base_url.removesuffix("/")
        credentials["base_url"] = base_url
        try:
            for _ in VannaTool.from_credentials(credentials, user_id="").invoke(
                tool_parameters={
                    "model": "chinook",
                    "db_type": "SQLite",
                    "url": f"{self._get_protocol_and_main_domain(credentials['base_url'])}/Chinook.sqlite",
                    "prompt": "What are the top 10 customers by sales?",
                }
            ):
                pass
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

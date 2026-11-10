from typing import Any

from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError

from spiderApp import Spider, SpiderError


class SpiderProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict[str, Any]) -> None:
        # GET /v1/data/credits checks the key without scraping, so saving a key spends nothing.
        try:
            app = Spider(api_key=credentials.get("spider_api_key"))
            app.get_credits()
        except SpiderError as e:
            if e.status_code == 402:
                # The key is valid; the account has no credits yet.
                return
            raise ToolProviderCredentialValidationError(str(e)) from e
        except ValueError as e:
            raise ToolProviderCredentialValidationError(str(e)) from e
        except Exception as e:
            raise ToolProviderCredentialValidationError(f"Could not reach the Spider API: {e}") from e

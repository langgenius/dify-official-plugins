from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from tools.scrape import ScrapeTool
from dify_plugin import ToolProvider


class FirecrawlProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict) -> None:
        try:
            ScrapeTool.from_credentials(credentials, user_id="").invoke(
                tool_parameters={"url": "https://google.com", "onlyIncludeTags": "title"}
            )
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
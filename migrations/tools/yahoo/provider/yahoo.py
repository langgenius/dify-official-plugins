from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from tools.ticker import YahooFinanceSearchTickerTool
from dify_plugin import ToolProvider


class YahooFinanceProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict) -> None:
        try:
            YahooFinanceSearchTickerTool.from_credentials(credentials, user_id="").invoke(
                tool_parameters={"ticker": "MSFT"}
            )
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))
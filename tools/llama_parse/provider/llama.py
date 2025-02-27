from dify_plugin import ToolProvider
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from llama_cloud_services import LlamaParse
from llama_cloud_services.parse.utils import ResultType


class LlamaParseProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict) -> None:
        try:
            parser = LlamaParse(
                api_key=credentials["llama_cloud_api_key"],
                result_type=ResultType.MD,
                language="en",
                ignore_errors=False,
            )
            res = parser.load_data("test_file/hello.pdf")
            assert len(res) == 1
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

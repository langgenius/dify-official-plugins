import requests
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import ToolProvider


def query_weather(city="Beijing", units="metric", language="zh_cn", api_key=None, timeout=10):
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": api_key, "units": units, "lang": language}
    return requests.get(url, params=params, timeout=timeout)


class OpenweatherProvider(ToolProvider):
    def _validate_credentials(self, credentials: dict) -> None:
        try:
            if "api_key" not in credentials or not credentials.get("api_key"):
                raise ToolProviderCredentialValidationError("Open weather API key is required.")
            apikey = credentials.get("api_key")
            try:
                response = query_weather(api_key=apikey)
                if response.status_code == 200:
                    pass
                else:
                    raise ToolProviderCredentialValidationError(response.json().get("info"))
            except Exception as e:
                raise ToolProviderCredentialValidationError("Open weather API Key is invalid. {}".format(e))
        except Exception as e:
            raise ToolProviderCredentialValidationError(str(e))

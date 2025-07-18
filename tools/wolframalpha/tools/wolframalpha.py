from typing import Any, Generator
from httpx import get
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin import Tool


class WolframAlphaTool(Tool):
    _base_url = "https://api.wolframalpha.com/v2/query"

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke tools
        """
        query = tool_parameters.get("query", "")
        if not query:
            yield self.create_text_message("Please input query")
        appid = self.runtime.credentials.get("appid", "")
        if not appid:
            raise ToolProviderCredentialValidationError("Please input appid")
        params = {"appid": appid, "input": query, "includepodid": "Result", "format": "plaintext", "output": "json"}
        finished = False
        result = None
        counter = 0
        while not finished and counter < 3:
            counter += 1
            try:
                response = get(self._base_url, params=params, timeout=20)
                response.raise_for_status()
                response_data = response.json()
            except Exception as e:
                raise e
            if "success" not in response_data["queryresult"] or response_data["queryresult"]["success"] != True:
                query_result = response_data.get("queryresult", {})
                if query_result.get("error"):
                    if "msg" in query_result["error"]:
                        if query_result["error"]["msg"] == "Invalid appid":
                            raise ToolProviderCredentialValidationError("Invalid appid")
                raise Exception("Failed to invoke tool")
            if "didyoumeans" in response_data["queryresult"]:
                query = ""
                max_score = 0
                for didyoumean in response_data["queryresult"]["didyoumeans"]:
                    if float(didyoumean["score"]) > max_score:
                        query = didyoumean["val"]
                        max_score = float(didyoumean["score"])
                params["input"] = query
            else:
                finished = True
                if "sources" in response_data["queryresult"]:
                    yield self.create_link_message(response_data["queryresult"]["sources"]["url"])
                elif "pods" in response_data["queryresult"]:
                    result = response_data["queryresult"]["pods"][0]["subpods"][0]["plaintext"]
        if not finished or not result:
            yield self.create_text_message("No result found")
        else:
            yield self.create_text_message(str(result))

from dify_plugin import OAICompatLargeLanguageModel


class ChuiziLargeLanguageModel(OAICompatLargeLanguageModel):
    def _update_credential(self, model: str, credentials: dict):
        credentials["endpoint_url"] = "https://api.chuizi.ai/v1"
        credentials["mode"] = self.get_model_mode(model).value
        schema = self.get_model_schema(model, credentials)
        if schema and schema.features:
            from dify_plugin.entities.model import ModelFeature

            if {ModelFeature.TOOL_CALL, ModelFeature.MULTI_TOOL_CALL}.intersection(
                schema.features
            ):
                credentials["function_calling_type"] = "tool_call"

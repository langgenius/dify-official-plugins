import json
from collections.abc import Generator, Mapping
from contextlib import contextmanager
from pathlib import Path

import requests
from dify_plugin.entities import I18nObject
from dify_plugin.entities.model import (
    AIModelEntity,
    FetchFrom,
    ModelType,
    ParameterRule,
    ParameterType,
)
from dify_plugin.errors.model import (
    InvokeAuthorizationError,
    InvokeBadRequestError,
    InvokeConnectionError,
    InvokeError,
    InvokeRateLimitError,
    InvokeServerUnavailableError,
)

from models._credentials import API_ORIGIN, validate_model_access

_REDIRECT_SCHEMAS: dict | None = None
_STATIC_MODELS: dict[str, set[str]] | None = None


def _redirect_data() -> dict:
    global _REDIRECT_SCHEMAS
    if _REDIRECT_SCHEMAS is None:
        shard_dir = Path(__file__).with_name("_redirect_schemas")
        index_path = shard_dir / "index.json"
        if index_path.is_file():
            index = json.loads(index_path.read_text(encoding="utf-8"))
            merged: dict[str, dict[str, dict]] = {}
            for shard_name in index.get("shards") or []:
                shard = json.loads((shard_dir / shard_name).read_text(encoding="utf-8"))
                for kind, entries in (shard.get("schemas") or {}).items():
                    if isinstance(entries, dict):
                        merged.setdefault(kind, {}).update(entries)
            _REDIRECT_SCHEMAS = {
                "families": index.get("families") or {},
                "schemas": merged,
            }
        else:
            path = Path(__file__).with_name("_redirect_schemas.json")
            _REDIRECT_SCHEMAS = (
                json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
            )
    return _REDIRECT_SCHEMAS


def _static_models(kind: str) -> set[str]:
    global _STATIC_MODELS
    if _STATIC_MODELS is None:
        root = Path(__file__).resolve().parent
        _STATIC_MODELS = {}
        for directory in root.iterdir():
            if directory.is_dir() and not directory.name.startswith(("_", ".")):
                _STATIC_MODELS[directory.name] = {
                    p.stem for p in directory.glob("*.yaml") if not p.name.startswith("_")
                }
    return _STATIC_MODELS.get(kind, set())


def redirect_family(model: str) -> str:
    return str((_redirect_data().get("families") or {}).get(model) or "")


class TokenerAPIModel:
    def validate_credentials(self, model: str, credentials: dict) -> None:
        validate_model_access(credentials, model)

    def get_customizable_model_schema(
        self, model: str, credentials: Mapping
    ) -> AIModelEntity | None:
        model_type = getattr(self, "model_type", None)
        kind = (
            model_type.value.replace("-", "_")
            if isinstance(model_type, ModelType)
            else str(model_type or "").replace("-", "_")
        )
        if not kind or model in _static_models(kind):
            return None
        schemas = (_redirect_data().get("schemas") or {}).get(kind) or {}
        if entry := schemas.get(model):
            return AIModelEntity.model_validate(entry)
        if kind == "llm" and model.startswith("ft:"):
            base = model.removeprefix("ft:").split(":", 1)[0]
            predefined = {item.model: item for item in self.predefined_models()}
            base_schema = predefined.get(base) or (
                AIModelEntity.model_validate(schemas[base]) if base in schemas else None
            )
            if base_schema is not None:
                return base_schema.model_copy(
                    deep=True,
                    update={
                        "model": model,
                        "label": I18nObject(en_us=model, zh_hans=model),
                        "fetch_from": FetchFrom.CUSTOMIZABLE_MODEL,
                    },
                )
        if kind == "llm" and model.startswith("claude-"):
            raw_max = credentials.get("max_tokens", 128000)
            max_limit = 128000
            if isinstance(raw_max, int | float | str) and not isinstance(raw_max, bool):
                try:
                    parsed = int(raw_max)
                    if parsed > 0:
                        max_limit = parsed
                except ValueError:
                    max_limit = 128000
            return AIModelEntity(
                model=model,
                label=I18nObject(en_us=model, zh_hans=model),
                model_type=ModelType.LLM,
                fetch_from=FetchFrom.CUSTOMIZABLE_MODEL,
                model_properties={"mode": "chat", "context_size": 200000},
                parameter_rules=[
                    ParameterRule(
                        name="max_tokens",
                        use_template="max_tokens",
                        default=4096,
                        min=1,
                        max=max_limit,
                        label=I18nObject(en_us="Max Tokens", zh_hans="最大标记"),
                        type=ParameterType.INT,
                    )
                ],
            )
        return None

    @property
    def _invoke_error_mapping(self) -> dict:
        return {}

    def _transform_invoke_error(self, error: Exception) -> InvokeError:
        if isinstance(error, InvokeError):
            return error
        return InvokeServerUnavailableError("Tokener.ai returned an invalid response")

    @contextmanager
    def _request(
        self, path: str, credentials: dict, **kwargs
    ) -> Generator[requests.Response, None, None]:
        with self._request_at(f"/v1/{path}", credentials, **kwargs) as response:
            yield response

    @contextmanager
    def _request_at(
        self,
        path: str,
        credentials: dict,
        *,
        timeout: tuple[int, int | None] = (10, 120),
        headers: dict | None = None,
        method: str = "POST",
        **kwargs,
    ) -> Generator[requests.Response, None, None]:
        try:
            request = requests.get if method == "GET" else requests.post
            with request(
                f"{API_ORIGIN}{path}",
                headers={**(headers or {}), "Authorization": f"Bearer {credentials['api_key']}"},
                allow_redirects=False,
                timeout=timeout,
                **kwargs,
            ) as response:
                status = response.status_code
                if status in {401, 403}:
                    raise InvokeAuthorizationError("Tokener.ai denied model access")
                if status == 429:
                    raise InvokeRateLimitError("Tokener.ai rate limit exceeded")
                if 400 <= status < 500:
                    raise InvokeBadRequestError(f"Tokener.ai rejected the request (HTTP {status})")
                if not 200 <= status < 300:
                    raise InvokeServerUnavailableError(f"Tokener.ai request failed (HTTP {status})")
                yield response
        except requests.exceptions.JSONDecodeError as ex:
            raise InvokeServerUnavailableError("Tokener.ai returned an invalid response") from ex
        except requests.RequestException as ex:
            raise InvokeConnectionError("Unable to reach Tokener.ai") from ex

    def _post(self, path: str, credentials: dict, payload: dict) -> dict:
        with self._request(path, credentials, json=payload) as response:
            result = response.json()
        if not isinstance(result, dict):
            raise InvokeServerUnavailableError("Tokener.ai returned an invalid response")
        return result

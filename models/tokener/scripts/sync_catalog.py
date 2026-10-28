#!/usr/bin/env python3

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote

if not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts import catalog_media
from scripts.catalog_schema import CatalogError, _decimal, _positive_int, _string

MAX_INPUT_BYTES = 5 * 1024 * 1024
FALLBACK_MAX_OUTPUT_TOKENS = 65536
DEFAULT_MAX_TOKENS = 8192
ROOT = Path(__file__).resolve().parents[1]
LLM_DIR = ROOT / "models" / "llm"
MODEL_TYPES = ("llm", "text_embedding", "rerank", "tts", "speech2text")
CATEGORY_TYPES = {
    "chat": "llm",
    "reasoning": "llm",
    "embedding": "text-embedding",
    "rerank": "rerank",
    "tts": "tts",
    "speech2text": "speech2text",
}
PARAMETER_PROFILES = json.loads((ROOT / "scripts" / "parameter_profiles.json").read_text())

CAPABILITIES = {
    "streaming",
    "tool_calling",
    "parallel_tool_calling",
    "streaming_tool_calls",
    "vision",
    "structured_output",
    "reasoning",
}
FEATURES = (
    ("tool_calling", "tool-call"),
    ("parallel_tool_calling", "multi-tool-call"),
    ("streaming_tool_calls", "stream-tool-call"),
    ("vision", "vision"),
    ("structured_output", "structured-output"),
)
REVISION_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")


def load_catalog(path: Path) -> Any:
    with path.open("rb") as handle:
        return decode_catalog(handle.read(MAX_INPUT_BYTES + 1))


def decode_catalog(body: bytes) -> Any:
    if len(body) > MAX_INPUT_BYTES:
        raise CatalogError("catalog snapshot exceeds 5 MiB")
    try:
        return json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as ex:
        if body.lstrip().startswith(b"<"):
            raise CatalogError(
                "catalog looks like an HTML login page. Re-authenticate and export JSON"
            ) from ex
        raise CatalogError("catalog snapshot is not valid JSON") from ex


def normalize_catalog(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise CatalogError("catalog must be an object")
    if payload.get("schemaVersion") == 1:
        return payload
    rows = payload.get("items")
    if not isinstance(rows, list):
        raise CatalogError("catalog needs model metadata; use --input with a complete JSON export")
    if any(not isinstance(row, dict) for row in rows):
        raise CatalogError("catalog items must be objects")
    unknown = [
        (row.get("category"), row.get("publicModelId"))
        for row in rows
        if row.get("enabled") is True
        and row.get("managedAvailable") is True
        and row.get("category") not in (*CATEGORY_TYPES, "decision")
    ]
    if unknown:
        detail = "; ".join(f"{category!r}: {model_id}" for category, model_id in unknown)
        raise CatalogError(f"unsupported catalog categories and public model IDs: {detail}")
    models = []
    for row in rows:
        if row.get("enabled") is not True or row.get("managedAvailable") is not True:
            continue
        category = row.get("category")
        if category == "decision":
            continue
        model = {
            "id": row.get("publicModelId"),
            "label": row.get("publicModelId"),
            "provider": row.get("provider"),
            "modelType": CATEGORY_TYPES[category],
            "mode": "chat",
            "contextSize": row.get("contextLength"),
            "maxOutputTokens": row.get("maxOutputTokens"),
            "capabilities": row.get("capabilities"),
            "deprecated": row.get("deprecated"),
            "pricing": {
                "currency": "USD",
                "inputPerMillion": row.get("inputPricePer1m"),
                "outputPerMillion": row.get("outputPricePer1m"),
                "cacheReadPerMillion": row.get("cachePricePer1m"),
            },
        }
        if category in ("tts", "speech2text"):
            model["audio"] = row.get("audioMetadata")
            model["pricing"] = {"currency": "USD", "rates": row.get("audioPrices")}
        models.append(model)
    models.sort(key=lambda model: _string(model["id"], "publicModelId"))
    digest = hashlib.sha256(json.dumps(models, sort_keys=True).encode()).hexdigest()
    return {"schemaVersion": 1, "catalogRevision": f"sha256:{digest}", "models": models}


def render_catalog(payload: Any, *, model_type: str = "llm") -> dict[str, str]:
    payload = normalize_catalog(payload)
    if payload.get("schemaVersion") != 1:
        raise CatalogError("catalog schemaVersion must be 1")

    revision = _string(payload.get("catalogRevision"), "catalogRevision")
    if REVISION_PATTERN.fullmatch(revision) is None:
        raise CatalogError("catalogRevision must be a sha256 digest")

    raw_models = payload.get("models")
    if not isinstance(raw_models, list):
        raise CatalogError("models must be an array")

    if model_type not in MODEL_TYPES:
        raise CatalogError(f"unsupported output model type: {model_type}")

    seen: set[str] = set()
    models: list[dict[str, Any]] = []
    for index, raw_model in enumerate(raw_models):
        if not isinstance(raw_model, dict):
            raise CatalogError(f"models[{index}] must be an object")

        model_id = _string(raw_model.get("id"), f"models[{index}].id")
        if model_id in seen:
            raise CatalogError(f"duplicate model id: {model_id}")
        seen.add(model_id)

        entry_type = raw_model.get("modelType")
        entry_type = "text_embedding" if entry_type == "text-embedding" else entry_type
        if entry_type not in MODEL_TYPES:
            raise CatalogError(f"unsupported model type for {model_id}: {entry_type}")
        if entry_type != model_type:
            continue
        if model_type in {"tts", "speech2text", "text_embedding", "rerank"}:
            validator = {
                "tts": catalog_media._validate_tts,
                "speech2text": catalog_media._validate_speech2text,
                "text_embedding": catalog_media._validate_embedding,
                "rerank": catalog_media._validate_rerank,
            }[model_type]
            validator(raw_model)
            models.append(raw_model)
            continue

        _string(raw_model.get("provider"), f"{model_id}.provider")
        if raw_model.get("mode") != "chat":
            raise CatalogError(f"{model_id}.mode must be chat")
        _positive_int(raw_model.get("contextSize"), f"{model_id}.contextSize")

        max_output_tokens = raw_model.get("maxOutputTokens")
        if max_output_tokens is not None:
            _positive_int(max_output_tokens, f"{model_id}.maxOutputTokens")

        capabilities = raw_model.get("capabilities")
        if not isinstance(capabilities, list) or any(
            not isinstance(capability, str) for capability in capabilities
        ):
            raise CatalogError(f"{model_id}.capabilities must be a string array")
        if len(capabilities) != len(set(capabilities)):
            raise CatalogError(f"{model_id}.capabilities contains duplicates")
        unknown = set(capabilities) - CAPABILITIES
        if unknown:
            raise CatalogError(
                f"{model_id}.capabilities contains unknown values: {sorted(unknown)}"
            )
        if "streaming" not in capabilities:
            raise CatalogError(f"{model_id}.capabilities must include streaming")

        pricing = raw_model.get("pricing")
        if not isinstance(pricing, dict):
            raise CatalogError(f"{model_id}.pricing must be an object")
        _string(pricing.get("currency"), f"{model_id}.pricing.currency")
        _decimal(pricing.get("inputPerMillion"), f"{model_id}.pricing.inputPerMillion")
        _decimal(pricing.get("outputPerMillion"), f"{model_id}.pricing.outputPerMillion")
        cache_price = pricing.get("cacheReadPerMillion")
        if cache_price is not None:
            _decimal(cache_price, f"{model_id}.pricing.cacheReadPerMillion")

        if not isinstance(raw_model.get("deprecated"), bool):
            raise CatalogError(f"{model_id}.deprecated must be a boolean")

        models.append(raw_model)

    files: dict[str, str] = {}
    ordered_models = sorted(models, key=lambda model: model["id"])
    render = {
        "llm": _render_model,
        "speech2text": catalog_media._render_speech2text,
        "tts": catalog_media._render_tts,
        "text_embedding": catalog_media._render_embedding,
        "rerank": catalog_media._render_rerank,
    }[model_type]
    for model in ordered_models:
        filename = f"{quote(model['id'], safe='._-')}.yaml"
        files[filename] = render(model)
    files["_position.yaml"] = _render_position(ordered_models)
    return files


def _render_model(model: dict[str, Any]) -> str:
    capabilities = set(model["capabilities"])
    features = [feature for capability, feature in FEATURES if capability in capabilities]
    if model["id"] == "qwen-long":
        features.append("document")
    pricing = model["pricing"]

    lines = [
        f"model: {json.dumps(model['id'], ensure_ascii=False)}",
        "label:",
        f"  en_US: {json.dumps(model['id'], ensure_ascii=False)}",
        f"  zh_Hans: {json.dumps(model['id'], ensure_ascii=False)}",
        "model_type: llm",
        "features:",
    ]
    lines.extend(f"  - {feature}" for feature in features)
    if not features:
        lines[-1] = "features: []"
    max_output_tokens = model.get("maxOutputTokens")
    if max_output_tokens is None:
        max_output_tokens = min(model["contextSize"], FALLBACK_MAX_OUTPUT_TOKENS)
    lines.extend(
        [
            "model_properties:",
            "  mode: chat",
            f"  context_size: {model['contextSize']}",
            "parameter_rules:",
            "  - name: max_tokens",
            "    use_template: max_tokens",
            f"    default: {min(DEFAULT_MAX_TOKENS, max_output_tokens)}",
            "    min: 1",
            f"    max: {max_output_tokens}",
        ]
    )
    profile = next(
        (
            profile
            for profile in PARAMETER_PROFILES
            if re.fullmatch(profile["pattern"], model["id"], re.IGNORECASE)
        ),
        {},
    )
    sampling = profile.get("sampling", [])
    if "reasoning" in capabilities and not profile.get("reasoning_sampling", False):
        sampling = []
    for name in sampling:
        minimum, maximum = {
            "temperature": (0, 2),
            "top_p": (profile.get("top_p_min", 0.01), 1),
            "presence_penalty": (-2, 2),
            "frequency_penalty": (-2, 2),
        }[name]
        lines.extend(
            [
                f"  - name: {name}",
                f"    use_template: {name}",
                f"    min: {minimum}",
                f"    max: {maximum}",
            ]
        )
    if profile.get("seed"):
        lines.extend(["  - name: seed", "    type: int", "    required: false"])
    efforts = profile.get("reasoning_efforts")
    if efforts and "reasoning" in capabilities:
        lines.extend(
            [
                "  - name: reasoning_effort",
                "    type: string",
                "    required: false",
                "    default: medium",
                "    options:",
                *(f"      - {effort}" for effort in efforts),
            ]
        )
    if "structured_output" in capabilities:
        lines.extend(
            [
                "  - name: response_format",
                "    label:",
                "      en_US: Response Format",
                "      zh_Hans: 回复格式",
                "    type: string",
                "    help:",
                "      en_US: Specify the format that the model must output.",
                "      zh_Hans: 指定模型必须输出的格式。",
                "    required: false",
                "    default: text",
                "    options:",
                "      - text",
                "      - json_object",
                "      - json_schema",
                "  - name: json_schema",
                "    use_template: json_schema",
            ]
        )
    lines.extend(
        [
            "pricing:",
            f"  input: {json.dumps(pricing['inputPerMillion'])}",
            f"  output: {json.dumps(pricing['outputPerMillion'])}",
            '  unit: "0.000001"',
            f"  currency: {json.dumps(pricing['currency'])}",
            f"deprecated: {str(model['deprecated']).lower()}",
        ]
    )
    return "\n".join(lines) + "\n"


def _render_position(models: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.extend(f"- {json.dumps(model['id'], ensure_ascii=False)}" for model in models)
    return "\n".join(lines) + "\n" if lines else "[]\n"


def sync_files(files: dict[str, str], *, check: bool, output_dir: Path = LLM_DIR) -> bool:
    current = {
        path.name: path.read_text(encoding="utf-8")
        for path in output_dir.glob("*.yaml")
        if path.is_file()
    }
    stale = set(current) - files.keys()
    changed = {name for name, content in files.items() if current.get(name) != content}

    if check:
        if changed or stale:
            for name in sorted(changed | stale):
                print(f"catalog drift: {output_dir.name}/{name}", file=sys.stderr)
            return False
        return True

    output_dir.mkdir(parents=True, exist_ok=True)
    for name in stale:
        (output_dir / name).unlink()
    for name in changed:
        (output_dir / name).write_text(files[name], encoding="utf-8")
    print(f"synced {len(files) - 1} {output_dir.name} models")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Tokener.ai models into Dify YAML")
    parser.add_argument(
        "--input", type=Path, required=True, help="complete Tokener catalog snapshot JSON"
    )
    parser.add_argument("--check", action="store_true", help="fail if generated files differ")
    parser.add_argument("--model-type", choices=(*MODEL_TYPES, "all"), default="all")
    args = parser.parse_args()

    try:
        payload = load_catalog(args.input)
        payload = normalize_catalog(payload)
        if not isinstance(payload.get("models"), list):
            raise CatalogError("models must be an array")
        if any(not isinstance(model, dict) for model in payload["models"]):
            raise CatalogError("models entries must be objects")
        kinds = MODEL_TYPES if args.model_type == "all" else (args.model_type,)
        outputs = {kind: render_catalog(payload, model_type=kind) for kind in kinds}
        results = [
            sync_files(files, check=args.check, output_dir=ROOT / "models" / kind)
            for kind, files in outputs.items()
        ]
        return 0 if all(results) else 1
    except (CatalogError, OSError) as ex:
        print(f"catalog sync failed: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

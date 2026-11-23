import copy
import json
import re
from pathlib import Path

import yaml
from dify_plugin.entities.model import (
    AIModelEntity,
    ModelFeature,
)

from models.llm._wire import TRANSPORT_FIELDS
from scripts.catalog_schema import CatalogError

SOURCE_PROVIDERS = {
    "openai": "openai",
    "gemini": "gemini",
    "anthropic": "anthropic",
    "tongyi": "tongyi",
    "x": "xai",
}
RULE_FIELDS = {
    "name",
    "use_template",
    "type",
    "required",
    "default",
    "min",
    "max",
    "precision",
    "options",
}


class _Dumper(yaml.SafeDumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


def load_source_contracts(root: Path) -> dict:
    contracts = {}
    for directory, family in SOURCE_PROVIDERS.items():
        manifest_path = root / directory / "manifest.yaml"
        try:
            manifest = yaml.safe_load(manifest_path.read_text())
        except (OSError, yaml.YAMLError) as error:
            raise CatalogError(f"Cannot read source provider: {manifest_path}") from error
        if (
            not isinstance(manifest, dict)
            or manifest.get("name") != directory
            or not isinstance(manifest.get("version"), str)
        ):
            raise CatalogError(f"Invalid source provider identity: {manifest_path}")
        paths = sorted((root / directory / "models" / "llm").glob("*.yaml"))
        if not any(not path.name.startswith("_") for path in paths):
            raise CatalogError(f"Source provider has no LLM models: {manifest_path}")
        for path in paths:
            if path.name.startswith("_"):
                continue
            try:
                model = yaml.safe_load(path.read_text())
            except (OSError, yaml.YAMLError) as error:
                raise CatalogError(f"Cannot read source model: {path}") from error
            identity = model.get("model") if isinstance(model, dict) else None
            if not isinstance(identity, str) or identity in contracts:
                raise CatalogError(f"Invalid or duplicate source model: {path}")
            contracts[identity] = {"family": family, "version": manifest["version"], "model": model}
    return contracts


def apply_source_contracts(files: dict[str, str], contracts: dict) -> dict[str, str]:
    providers = {}
    for name, body in files.items():
        if name.startswith("_"):
            continue
        generated = yaml.safe_load(body)
        identity = generated["model"]
        if identity not in contracts:
            continue
        contract = contracts[identity]
        source = contract["model"]
        source_rules = {
            rule["name"]: {key: value for key, value in rule.items() if key in RULE_FIELDS}
            for rule in source.get("parameter_rules", [])
            if rule["name"] not in TRANSPORT_FIELDS
        }
        rules = [
            source_rules.get(rule["name"], rule)
            for rule in generated["parameter_rules"]
            if rule["name"] not in TRANSPORT_FIELDS
            and not (
                contract["family"] == "anthropic"
                and rule["name"] in {"prompt_caching_ttl", "task_budget", "speed"}
                and rule["name"] not in source_rules
            )
        ]
        names = {rule["name"] for rule in rules}
        rules.extend(rule for name, rule in source_rules.items() if name not in names)
        output_cap = next(
            rule["max"] for rule in generated["parameter_rules"] if rule["name"] == "max_tokens"
        )
        for rule in rules:
            if rule.get("use_template") == "max_tokens":
                rule["max"] = min(rule.get("max", output_cap), output_cap)
                rule["default"] = min(rule.get("default", rule["max"]), rule["max"])
        generated["parameter_rules"] = rules
        generated["features"] = list(
            dict.fromkeys([*generated.get("features", []), *source.get("features", [])])
        )
        for section, following in (
            ("parameter_rules", "pricing"),
            ("features", "model_properties"),
        ):
            replacement = yaml.dump(
                {section: generated[section]},
                Dumper=_Dumper,
                sort_keys=False,
                allow_unicode=True,
                width=100,
            )
            body = re.sub(
                rf"(?ms)^{section}:.*?(?=^{following}:)",
                lambda _, value=replacement: value,
                body,
            )
        files[name] = body
        if contract["family"] == "tongyi" and not identity.startswith(("qwen", "qwq-", "qvq-")):
            providers[identity] = "tongyi"
    files["_provider_models.json"] = json.dumps(providers, sort_keys=True, indent=2) + "\n"
    return files


_GEMINI_FILE_FEATURES = {
    ModelFeature.VISION.value,
    ModelFeature.DOCUMENT.value,
    ModelFeature.VIDEO.value,
    ModelFeature.AUDIO.value,
}
REDIRECT_MODEL_TYPES = ("llm", "text_embedding", "rerank", "tts", "speech2text", "moderation")


def _slim_i18n(val: object, fallback: str) -> dict[str, str]:
    if isinstance(val, dict):
        en = str(val.get("en_US") or val.get("en_us") or fallback)
        zh = str(val.get("zh_Hans") or val.get("zh_hans") or en)
        return {"en_US": en, "zh_Hans": zh}
    text = str(val or fallback)
    return {"en_US": text, "zh_Hans": text}


def _slim_model_entry(raw: dict, *, add_inline_file: bool) -> dict:
    model_id = str(raw["model"])
    slim: dict = {
        "model": model_id,
        "label": _slim_i18n(raw.get("label"), model_id),
        "model_type": raw.get("model_type"),
    }
    for key in ("features", "model_properties", "pricing", "deprecated"):
        if key in raw and raw[key] is not None:
            slim[key] = copy.deepcopy(raw[key])
    rules = []
    for rule in raw.get("parameter_rules") or []:
        sr = {k: copy.deepcopy(rule[k]) for k in RULE_FIELDS if k in rule}
        if "use_template" not in sr:
            sr["label"] = _slim_i18n(rule.get("label"), str(rule.get("name") or ""))
        rules.append(sr)
    if add_inline_file:
        rules.append(
            {
                "name": "use_inline_file",
                "type": "boolean",
                "required": True,
                "default": False,
                "label": {"en_US": "Use inline file mode", "zh_Hans": "使用内嵌文件模式"},
            }
        )
    if rules:
        slim["parameter_rules"] = rules
    AIModelEntity.model_validate(copy.deepcopy(slim))
    return slim


def export_redirect_schemas(root: Path, target_models_dir: Path | None = None) -> dict:
    static_by_kind: dict[str, set[str]] = {}
    if target_models_dir is not None and target_models_dir.is_dir():
        for kind in REDIRECT_MODEL_TYPES:
            kd = target_models_dir / kind
            if kd.is_dir():
                static_by_kind[kind] = {
                    p.stem for p in kd.glob("*.yaml") if not p.name.startswith("_")
                }
    families: dict[str, str] = {}
    schemas: dict[str, dict[str, dict]] = {}
    for directory, family in SOURCE_PROVIDERS.items():
        provider_dir = root / directory / "models"
        for kind in REDIRECT_MODEL_TYPES:
            kind_dir = provider_dir / kind
            if not kind_dir.is_dir():
                continue
            for path in sorted(kind_dir.glob("*.yaml")):
                if path.name.startswith("_"):
                    continue
                raw = yaml.safe_load(path.read_text(encoding="utf-8"))
                entity = AIModelEntity.model_validate(copy.deepcopy(raw))
                if kind == "llm":
                    families[entity.model] = family
                if entity.model in static_by_kind.get(kind, set()):
                    continue
                feature_values = {getattr(f, "value", f) for f in (entity.features or [])}
                rule_names = {r.name for r in (entity.parameter_rules or [])}
                add_inline = bool(
                    family == "gemini"
                    and kind == "llm"
                    and (feature_values & _GEMINI_FILE_FEATURES)
                    and "use_inline_file" not in rule_names
                )
                schemas.setdefault(kind, {})[entity.model] = _slim_model_entry(
                    raw, add_inline_file=add_inline
                )
    return {"families": families, "schemas": schemas}


def _render_compact_shard(payload: dict[str, dict[str, dict]]) -> str:
    lines = ['{"schemas":{']
    kinds = sorted(payload)
    for k_idx, kind in enumerate(kinds):
        lines.append(f'"{kind}":{{')
        models = sorted(payload[kind])
        for m_idx, m_name in enumerate(models):
            comma = "," if m_idx + 1 < len(models) else ""
            dumped = json.dumps(
                payload[kind][m_name], ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            lines.append(f"{json.dumps(m_name)}:{dumped}{comma}")
        k_comma = "," if k_idx + 1 < len(kinds) else ""
        lines.append(f"}}{k_comma}")
    lines.append("}}\n")
    return "\n".join(lines)


def _pack_redirect_shards(schemas: dict[str, dict[str, dict]], max_shard_bytes: int) -> list[str]:
    shards: list[str] = []
    current: dict[str, dict[str, dict]] = {}
    for kind in sorted(schemas):
        for model_name in sorted(schemas[kind]):
            entry = schemas[kind][model_name]
            candidate = {k: dict(v) for k, v in current.items()}
            candidate.setdefault(kind, {})[model_name] = entry
            rendered = _render_compact_shard(candidate)
            if current and len(rendered.encode("utf-8")) > max_shard_bytes:
                shards.append(_render_compact_shard(current))
                current = {kind: {model_name: entry}}
            else:
                current = candidate
    if current:
        shards.append(_render_compact_shard(current))
    return shards


def sync_redirect_schemas(
    root: Path,
    output_dir: Path,
    *,
    check: bool = False,
    max_shard_bytes: int = 18000,
) -> bool:
    bundle = export_redirect_schemas(root, target_models_dir=output_dir.parent)
    packed = _pack_redirect_shards(bundle["schemas"], max_shard_bytes)
    shard_files = {f"shard_{idx:02d}.json": text for idx, text in enumerate(packed)}
    index_rendered = (
        json.dumps(
            {"families": bundle["families"], "shards": sorted(shard_files)},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    )
    expected = {"index.json": index_rendered, **shard_files}
    if check:
        if not output_dir.is_dir():
            return False
        existing = {p.name for p in output_dir.iterdir() if p.is_file()}
        if existing != set(expected):
            return False
        return all(
            (output_dir / name).read_text(encoding="utf-8") == content
            for name, content in expected.items()
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    for stale in list(output_dir.iterdir()):
        if stale.is_file() and stale.name not in expected:
            stale.unlink()
    for name, content in expected.items():
        (output_dir / name).write_text(content, encoding="utf-8")
    return True


if __name__ == "__main__":
    plugin_root = Path(__file__).resolve().parents[1]
    source_root = plugin_root.parent
    sync_redirect_schemas(source_root, plugin_root / "models" / "_redirect_schemas")

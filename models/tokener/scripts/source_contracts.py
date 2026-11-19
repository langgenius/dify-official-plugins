import json
import re
from pathlib import Path

import yaml

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
                and rule["name"] in {"prompt_caching_ttl", "task_budget"}
                and rule["name"] not in source_rules
            )
        ]
        names = {rule["name"] for rule in rules}
        rules.extend(rule for name, rule in source_rules.items() if name not in names)
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

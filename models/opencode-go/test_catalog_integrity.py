"""Model catalog integrity regression tests (no network).

Guards the models/llm YAML catalog (0.5.0: added claude-haiku-5-5,
longcat-2.5-preview-free, space-bunny; removed space-bunny-free):

- every *.yaml parses safely via the plugin's own loader
- each YAML's ``model:`` field matches its filename
- _position.yaml matches the YAML file set in both directions
- no duplicate model names
- expected 0.5.0 membership (space-bunny-free stays gone)
- manifest.yaml / pyproject.toml / DEFAULT_USER_AGENT versions agree
"""
import pathlib
import tomllib

from dify_plugin.core.utils.yaml_loader import load_yaml_file

from models.llm.session_headers import DEFAULT_USER_AGENT

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent
LLM_DIR = PLUGIN_ROOT / "models" / "llm"
POSITION_FILE = LLM_DIR / "_position.yaml"
# Bump together with manifest.yaml / pyproject.toml / DEFAULT_USER_AGENT on release.
EXPECTED_VERSION = "0.5.0"


def _model_yaml_files() -> list[pathlib.Path]:
    return sorted(p for p in LLM_DIR.glob("*.yaml") if p.name != "_position.yaml")


def _position_names() -> list:
    data = load_yaml_file(str(POSITION_FILE))
    assert isinstance(data, list), f"_position.yaml must parse to a list, got {type(data).__name__}"
    return data


def test_all_yaml_files_parse() -> None:
    files = sorted(LLM_DIR.glob("*.yaml"))
    assert files, f"no YAML files found under {LLM_DIR}"
    problems = []
    for path in files:
        try:
            data = load_yaml_file(str(path))
        except Exception as exc:  # noqa: BLE001 - report every bad file at once
            problems.append(f"{path.name}: {exc}")
            continue
        if path.name == "_position.yaml":
            if not isinstance(data, list):
                problems.append(f"{path.name}: expected list, got {type(data).__name__}")
        elif not isinstance(data, dict) or not data:
            problems.append(f"{path.name}: expected non-empty mapping, got {type(data).__name__}")
    assert not problems, "unparseable YAML: " + "; ".join(problems)


def test_model_field_matches_filename() -> None:
    problems = []
    for path in _model_yaml_files():
        data = load_yaml_file(str(path))
        model = data.get("model") if isinstance(data, dict) else None
        if model != path.stem:
            problems.append(f"{path.name}: model={model!r}")
    assert not problems, "model/filename mismatch: " + "; ".join(problems)


def test_position_yaml_matches_model_files() -> None:
    names = _position_names()
    assert all(isinstance(n, str) and n.strip() for n in names), (
        "_position.yaml entries must be non-empty strings"
    )
    duplicates = sorted({n for n in names if names.count(n) > 1})
    assert not duplicates, f"duplicate entries in _position.yaml: {duplicates}"
    position_set = set(names)
    file_set = {p.stem for p in _model_yaml_files()}
    orphan_refs = sorted(position_set - file_set)
    unlisted_files = sorted(file_set - position_set)
    assert not orphan_refs, f"_position.yaml references missing YAML files: {orphan_refs}"
    assert not unlisted_files, f"YAML files not listed in _position.yaml: {unlisted_files}"


def test_no_duplicate_model_names() -> None:
    seen: dict = {}
    duplicates = []
    for path in _model_yaml_files():
        model = load_yaml_file(str(path)).get("model")
        if model in seen:
            duplicates.append(f"{model!r} in {seen[model]} and {path.name}")
        seen[model] = path.name
    assert not duplicates, "duplicate model names: " + "; ".join(duplicates)


def test_0_5_0_model_membership() -> None:
    file_set = {p.stem for p in _model_yaml_files()}
    position_set = set(_position_names())
    for name in ("claude-haiku-5-5", "longcat-2.5-preview-free", "space-bunny"):
        assert name in file_set, f"expected model YAML missing: {name}.yaml"
        assert name in position_set, f"expected model missing from _position.yaml: {name}"
    # Removed model must not creep back in via any catalog entry point.
    assert "space-bunny-free" not in file_set, "deleted space-bunny-free.yaml must stay removed"
    assert "space-bunny-free" not in position_set, (
        "deleted space-bunny-free must stay out of _position.yaml"
    )
    declared_models = {load_yaml_file(str(p)).get("model") for p in _model_yaml_files()}
    assert "space-bunny-free" not in declared_models, (
        "no YAML may declare model: space-bunny-free"
    )


def test_version_consistency() -> None:
    manifest_version = str(load_yaml_file(str(PLUGIN_ROOT / "manifest.yaml")).get("version"))
    with (PLUGIN_ROOT / "pyproject.toml").open("rb") as fh:
        project_version = str(tomllib.load(fh)["project"]["version"])
    assert manifest_version == project_version, (
        f"manifest.yaml version {manifest_version!r} != pyproject.toml version {project_version!r}"
    )
    assert manifest_version == EXPECTED_VERSION, (
        f"version {manifest_version!r} != expected {EXPECTED_VERSION!r}; "
        "bump EXPECTED_VERSION together with the release files"
    )
    assert DEFAULT_USER_AGENT == f"dify-opencode-go-plugin/{manifest_version}", (
        f"DEFAULT_USER_AGENT {DEFAULT_USER_AGENT!r} out of sync with version {manifest_version!r}"
    )


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print("PASS", t.__name__)
    print("catalog integrity tests OK", len(tests))

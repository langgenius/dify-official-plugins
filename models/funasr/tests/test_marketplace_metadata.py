import re
import tomllib
from pathlib import Path


PLUGIN_DIR = Path(__file__).resolve().parents[1]
MODEL_DIR = PLUGIN_DIR / "models" / "speech2text"
PREDEFINED_MODELS = (
    "sensevoice.yaml",
    "paraformer.yaml",
    "paraformer-en.yaml",
    "fun-asr-nano.yaml",
)


def _read(relative_path: str) -> str:
    return (PLUGIN_DIR / relative_path).read_text(encoding="utf-8")


def test_marketplace_version_is_bumped_consistently():
    manifest = _read("manifest.yaml")
    pyproject = tomllib.loads(_read("pyproject.toml"))
    lock = tomllib.loads(_read("uv.lock"))

    manifest_version = re.search(r"^version:\s*(\S+)\s*$", manifest, re.MULTILINE)
    locked_project = next(
        package
        for package in lock["package"]
        if package["name"] == "funasr" and package.get("source") == {"virtual": "."}
    )

    assert manifest_version is not None
    versions = {
        manifest_version.group(1),
        pyproject["project"]["version"],
        locked_project["version"],
    }
    assert len(versions) == 1
    version = next(iter(versions))
    assert tuple(int(part) for part in version.split(".")) >= (0, 1, 1)


def test_public_copy_scopes_benchmark_and_released_checkpoint():
    readme = _read("README.md")
    public_copy = "\n".join(
        (readme, _read("manifest.yaml"), _read("provider/funasr.yaml"))
    )

    assert "170x faster than Whisper" not in public_copy
    assert "比 Whisper 快 170 倍" not in public_copy
    assert "50+ languages" not in public_copy

    assert "170x real-time" in readme
    assert "192-minute benchmark" in readme
    assert "https://modelscope.github.io/FunASR/benchmark.html" in readme
    assert "Mandarin, Cantonese, English, Japanese, and Korean" in readme


def test_predefined_upload_limits_match_customizable_models():
    for filename in PREDEFINED_MODELS:
        text = (MODEL_DIR / filename).read_text(encoding="utf-8")
        assert re.search(r"^\s*file_upload_limit:\s*25\s*$", text, re.MULTILINE)

    model_source = _read("models/speech2text/speech2text.py")
    assert "ModelPropertyKey.FILE_UPLOAD_LIMIT: 25" in model_source


def test_readme_installs_default_server_dependencies_and_model():
    readme = _read("README.md")

    assert 'pip install "funasr>=1.3.26" fastapi uvicorn python-multipart' in readme
    assert "funasr-server --device cuda --model sensevoice" in readme
    assert "http://localhost:8000/v1" in readme

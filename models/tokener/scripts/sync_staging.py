import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IDENTITY_FILES = {"PRIVACY.md", "README.md", "_assets/tokener.svg"}
STAGING_ASSETS = {"_assets/tokener-small.svg"}
IGNORED_DIRS = {".venv", "venv", "__pycache__", ".pytest_cache", ".ruff_cache", ".local"}
REPLACEMENTS = {
    "manifest.yaml": {
        "name: tokener\n": "name: tokener-staging\n",
        "  en_US: Tokener.ai\n": "  en_US: Tokener.ai (Staging)\n",
        "  zh_Hans: Tokener.ai\n": "  zh_Hans: Tokener.ai（测试环境）\n",
        "  en_US: Tokener.ai model provider for Dify.\n": (
            "  en_US: Staging-only test package; not for Marketplace or production use.\n"
        ),
        "  zh_Hans: Tokener.ai 的 Dify 模型插件。\n": (
            "  zh_Hans: 仅限测试环境的独立插件包，不用于 Marketplace 或生产环境。\n"
        ),
    },
    "provider/tokener.yaml": {
        "  en_US: Tokener.ai\n": "  en_US: Tokener.ai (Staging)\n",
        "  zh_Hans: Tokener.ai\n": "  zh_Hans: Tokener.ai（测试环境）\n",
        "icon_small:\n  en_US: tokener.svg\n": "icon_small:\n  en_US: tokener-small.svg\n",
        'background: "#F7F5EE"\n': 'background: "#FEF3C7"\n',
        "    en_US: Get your API key from Tokener.ai\n": (
            "    en_US: Get a Tokener staging API key\n"
        ),
        "    zh_Hans: 获取 Tokener.ai API Key\n": "    zh_Hans: 获取 Tokener 测试环境 API Key\n",
        "    en_US: https://console.tokener.ai/keys\n": (
            "    en_US: https://console-staging.tokener.dev/keys\n"
        ),
    },
    "models/_credentials.py": {
        'API_ORIGIN = "https://api.tokener.ai"\n': (
            'API_ORIGIN = "https://api-staging.tokener.dev"\n'
        ),
    },
}


def files(directory: Path) -> dict[str, Path]:
    result = {}
    for parent, subdirs, names in directory.walk():
        subdirs[:] = sorted(set(subdirs) - IGNORED_DIRS)
        for name in sorted(names):
            path = parent / name
            if path.suffix in {".pyc", ".pyo", ".difypkg"} or name in {".env", ".DS_Store"}:
                continue
            relative = path.relative_to(directory).as_posix()
            if path.is_symlink():
                raise ValueError(f"Unexpected symlink: {relative}")
            result[relative] = path
    return result


def sync(source: Path, target: Path, *, check: bool) -> list[str]:
    originals, current = files(source), files(target)
    extra = sorted(set(current) - set(originals) - STAGING_ASSETS)
    unavailable = sorted((IDENTITY_FILES | STAGING_ASSETS) - current.keys())
    if extra or unavailable:
        return [
            *(f"unexpected {name}" for name in extra),
            *(f"missing {name}" for name in unavailable),
        ]
    drift = []
    for name, path in sorted(originals.items()):
        if name in IDENTITY_FILES:
            continue
        data = path.read_bytes()
        if name in REPLACEMENTS:
            for before, after in REPLACEMENTS[name].items():
                old = before.encode()
                if data.count(old) != 1:
                    raise ValueError(
                        f"Expected one staging substitution in {name}: {before.strip()}"
                    )
                data = data.replace(old, after.encode())
        destination = target / name
        if name in current and destination.read_bytes() == data:
            continue
        if check:
            drift.append(name)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
    return drift


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Mirror Tokener into the independent staging plugin"
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        drift = sync(ROOT.parent / "tokener", ROOT.parent / "tokener-staging", check=args.check)
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1
    for name in drift:
        print(f"staging drift: {name}", file=sys.stderr)
    return int(bool(drift))


if __name__ == "__main__":
    raise SystemExit(main())

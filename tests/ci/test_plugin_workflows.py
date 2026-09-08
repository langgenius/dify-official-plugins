"""Run with: uv run --no-project --with pyyaml python tests/ci/test_plugin_workflows.py."""

import os
import subprocess
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
TOOLKIT_SHA = "1234567890abcdef1234567890abcdef12345678"
MOCK_COMMANDS = """
gh() {
  case "$1 $2" in
    "api repos/langgenius/dify-marketplace-toolkit/commits/HEAD")
      printf '%s\\n' "$MOCK_TOOLKIT"
      return "${MOCK_TOOLKIT_STATUS:-0}" ;;
    "release view")
      printf '%s\\n' "$MOCK_CLI"
      return "${MOCK_CLI_STATUS:-0}" ;;
    "repo clone")
      mkdir "${@: -1}"
      return "${MOCK_CLONE_STATUS:-0}" ;;
    *) return 2 ;;
  esac
}
git() {
  printf '%s\\n' "$@" > checkout-args
  return "${MOCK_GIT_STATUS:-0}"
}
"""


def main():
    for filename in ("pre-pr-check-per-plugin.yaml", "upload-merged-plugin.yaml"):
        workflow = yaml.safe_load((ROOT / ".github/workflows" / filename).read_text())
        steps = {
            step.get("name"): step
            for job in workflow["jobs"].values()
            for step in job["steps"]
        }
        assert steps["Clone Marketplace Toolkit"]["env"]["TOOLKIT_SHA"] == "${{ steps.external.outputs.toolkit_sha }}"
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            output = workdir / "github-output"
            env = {
                "PATH": os.environ["PATH"],
                "GITHUB_OUTPUT": str(output),
                "TOOLKIT_SHA": TOOLKIT_SHA,
                "MOCK_TOOLKIT": TOOLKIT_SHA,
                "MOCK_CLI": "v1.2.3",
            }

            def run(step, overrides=None):
                return subprocess.run(
                    ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", MOCK_COMMANDS + steps[step]["run"]],
                    cwd=workdir,
                    env=env | (overrides or {}),
                    capture_output=True,
                    text=True,
                )

            # Empty results also cover null fields filtered by gh's // empty.
            for overrides in (
                {"MOCK_TOOLKIT_STATUS": "1"},
                {"MOCK_CLI_STATUS": "1"},
                {"MOCK_TOOLKIT": ""},
                {"MOCK_CLI": ""},
            ):
                result = run("Resolve external tool versions", overrides)
                assert result.returncode != 0, (filename, overrides)
                assert not output.exists() or not output.read_text(), (filename, overrides)

            result = run("Resolve external tool versions")
            assert result.returncode == 0, (filename, result.stderr)
            assert output.read_text().splitlines() == [f"toolkit_sha={TOOLKIT_SHA}", "cli_tag=v1.2.3"]

            for restored_cache in (False, True):
                stale = workdir / ".scripts" / "stale-cache"
                if restored_cache:
                    stale.write_text("previous toolkit and CLI")
                result = run("Clone Marketplace Toolkit")
                assert result.returncode == 0, (filename, restored_cache, result.stderr)
                assert (workdir / ".scripts").is_dir() and not stale.exists()
                assert (workdir / "checkout-args").read_text().splitlines() == ["-C", ".scripts", "checkout", TOOLKIT_SHA]

            for overrides in ({"MOCK_CLONE_STATUS": "1"}, {"MOCK_GIT_STATUS": "1"}):
                result = run("Clone Marketplace Toolkit", overrides)
                assert result.returncode != 0, (filename, overrides)
        print(f"{filename}: version resolution and cache initialization passed")


if __name__ == "__main__":
    main()

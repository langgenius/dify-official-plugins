"""Live validator for OrcaRouter embedding + TTS models.

Probes each predefined embedding via POST /v1/embeddings and each TTS via
POST /v1/audio/speech. Mirrors validate_classification.py's pattern of
distinguishing plugin bugs from environment/upstream issues.

Usage:
    cd <plugin-root>
    export ORCAROUTER_API_KEY=sk-...
    python tests/validate_embedding_tts.py
    python tests/validate_embedding_tts.py --type embedding
    python tests/validate_embedding_tts.py --type tts --timeout 600
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests
import yaml

PLUGIN_ROOT = Path(__file__).parent.parent
EMBED_DIR = PLUGIN_ROOT / "models" / "text_embedding"
TTS_DIR = PLUGIN_ROOT / "models" / "tts"
DEFAULT_ENDPOINT = "https://api.orcarouter.ai/v1"

ENV_ERROR_SIGNALS = [
    "organization must be verified",
    "Read timed out",
    "Connection refused",
    "rate limit",
    "Rate limit",
    "quota",
    "insufficient_quota",
    "no available channel",
    "all channels failed",
    "channel quota",
    "model is not available",
]


def classify_error(msg: str) -> str:
    lower = msg.lower()
    return "env" if any(s.lower() in lower for s in ENV_ERROR_SIGNALS) else "plugin"


def load_models(d: Path) -> list[str]:
    pos = d / "_position.yaml"
    if not pos.exists():
        return []
    return yaml.safe_load(pos.read_text(encoding="utf-8")) or []


def default_voice_for(model: str) -> str:
    yaml_path = TTS_DIR / (model.replace("/", "-") + ".yaml")
    if not yaml_path.exists():
        return "alloy"
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return data["model_properties"].get("default_voice", "alloy")


def probe_embedding(api_key: str, endpoint: str, model: str, timeout: int) -> tuple[str, str]:
    body = {"model": model, "input": "Hello from OrcaRouter plugin validation."}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        r = requests.post(f"{endpoint}/embeddings", headers=headers, json=body, timeout=timeout)
    except requests.RequestException as e:
        msg = f"network error: {e}"
        return ("warn_env" if classify_error(msg) == "env" else "fail_plugin", msg)

    if r.status_code == 200:
        try:
            data = r.json()
            embed = data["data"][0]["embedding"]
            return "pass", f"OK ({len(embed)}-dim vector)"
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            return "fail_plugin", f"200 but bad body: {e}"

    try:
        err = r.json().get("error", {}).get("message") or r.text[:200]
    except json.JSONDecodeError:
        err = r.text[:200]
    full_msg = f"HTTP {r.status_code}: {err}"
    return ("warn_env" if classify_error(err) == "env" else "fail_plugin", full_msg)


def probe_tts(api_key: str, endpoint: str, model: str, timeout: int) -> tuple[str, str]:
    body = {
        "model": model,
        "input": "Hello.",
        "voice": default_voice_for(model),
        "response_format": "mp3",
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        r = requests.post(f"{endpoint}/audio/speech", headers=headers, json=body, timeout=timeout)
    except requests.RequestException as e:
        msg = f"network error: {e}"
        return ("warn_env" if classify_error(msg) == "env" else "fail_plugin", msg)

    if r.status_code == 200:
        size = len(r.content)
        if size < 100:
            return "fail_plugin", f"200 but suspiciously small audio: {size} bytes"
        return "pass", f"OK ({size} bytes mp3)"

    try:
        err = r.json().get("error", {}).get("message") or r.text[:200]
    except json.JSONDecodeError:
        err = r.text[:200]
    full_msg = f"HTTP {r.status_code}: {err}"
    return ("warn_env" if classify_error(err) == "env" else "fail_plugin", full_msg)


def run(probe_fn, label: str, models: list[str], api_key: str, endpoint: str, sleep: float, timeout: int):
    print(f"\n=== {label} ({len(models)} models) ===")
    results = []
    for m in models:
        status, msg = probe_fn(api_key, endpoint, m, timeout)
        emoji = {"pass": "PASS", "fail_plugin": "FAIL", "warn_env": "WARN"}[status]
        print(f"[{emoji}] {m}: {msg}")
        results.append((m, status, msg))
        time.sleep(sleep)
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--type", choices=["embedding", "tts", "both"], default="both")
    parser.add_argument("--endpoint", default=os.getenv("ORCAROUTER_API_BASE_URL", DEFAULT_ENDPOINT))
    parser.add_argument("--sleep", type=float, default=0.5)
    parser.add_argument("--timeout", type=int, default=300, help="HTTP timeout per request in seconds (default 300)")
    args = parser.parse_args()

    api_key = os.getenv("ORCAROUTER_API_KEY")
    if not api_key:
        print("ERROR: ORCAROUTER_API_KEY env var required", file=sys.stderr)
        sys.exit(2)

    print(f"Endpoint: {args.endpoint}")
    all_results = []

    if args.type in ("embedding", "both"):
        models = load_models(EMBED_DIR)
        all_results += run(probe_embedding, "Embedding (POST /v1/embeddings)", models, api_key, args.endpoint, args.sleep, args.timeout)

    if args.type in ("tts", "both"):
        models = load_models(TTS_DIR)
        all_results += run(probe_tts, "TTS (POST /v1/audio/speech)", models, api_key, args.endpoint, args.sleep, args.timeout)

    print()
    print("=" * 70)
    passed = sum(1 for _, s, _ in all_results if s == "pass")
    failed = sum(1 for _, s, _ in all_results if s == "fail_plugin")
    warned = sum(1 for _, s, _ in all_results if s == "warn_env")
    print(f"PASSED:           {passed} / {len(all_results)}")
    print(f"FAIL (plugin):    {failed}")
    print(f"WARN (env/infra): {warned}")
    if failed:
        print("\nReal plugin failures (suggest YAML/code fix):")
        for m, s, msg in all_results:
            if s == "fail_plugin":
                print(f"  - {m}: {msg}")
    if warned:
        print("\nEnvironment / upstream issues (NOT plugin bugs):")
        for m, s, msg in all_results:
            if s == "warn_env":
                print(f"  - {m}: {msg}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()

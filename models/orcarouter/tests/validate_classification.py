"""L4 classification validator (run from CLI, not via pytest).

For each model YAML in models/llm/, send a minimal chat request to OrcaRouter
with the parameters our YAML claims are supported. Report any 400 errors that
suggest mis-classification (e.g., a model in plain_chat bucket that rejects
temperature should be moved to openai_o bucket).

Usage:
    cd <plugin-root>
    export ORCAROUTER_API_KEY=sk-...
    python tests/validate_classification.py
    python tests/validate_classification.py --models openai/gpt-5 anthropic/claude-opus-4.7
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

LLM_DIR = Path(__file__).parent.parent / "models" / "llm"
DEFAULT_ENDPOINT = "https://api.orcarouter.ai/v1"


def load_yaml(model_id: str) -> dict | None:
    fname = model_id.replace("/", "-") + ".yaml"
    path = LLM_DIR / fname
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def build_test_payload(model_id: str, yaml_data: dict) -> dict:
    """Construct a chat completion payload exercising every param our YAML lists.

    Mirrors llm.py's payload shape:
      - flat `reasoning_effort` (NOT nested reasoning block)
      - Anthropic thinking left OFF (we just want a smoke test)
      - skips orcarouter_* params (tested separately)

    Special cases:
      - kimi-k2.6: temperature MUST be 1
    """
    params = {rule["name"]: rule for rule in yaml_data.get("parameter_rules", [])}
    body: dict = {
        "model": model_id,
        "messages": [{"role": "user", "content": "Reply with just 'ok'."}],
        # stream: True is forced by probe_model() (some upstreams require it)
    }
    if "max_tokens" in params:
        body["max_tokens"] = 10
    if "temperature" in params:
        # Respect param-rule constraints (kimi-k2.6 fixed at 1)
        rule = params["temperature"]
        if rule.get("min") == rule.get("max"):
            body["temperature"] = rule.get("default") or rule.get("min")
        else:
            body["temperature"] = 0.5
    if "top_p" in params:
        rule = params["top_p"]
        if rule.get("min") == rule.get("max"):
            body["top_p"] = rule.get("default") or rule.get("min")
        else:
            body["top_p"] = 0.9
    if "top_k" in params:
        body["top_k"] = 40
    if "reasoning_effort" in params:
        body["reasoning_effort"] = "low"  # flat field, OpenAI-native
    # enable_thinking is left OFF in this smoke test
    if "presence_penalty" in params:
        body["presence_penalty"] = 0.0
    if "frequency_penalty" in params:
        body["frequency_penalty"] = 0.0
    return body


# Errors that indicate user/upstream environment problems, NOT plugin bugs.
# Validator treats these as WARN (not FAIL) so classification correctness is
# distinguishable from infra/account issues.
ENV_ERROR_SIGNALS = [
    "organization must be verified",  # OpenAI gpt-5 / o-series org gate
    "Read timed out",                  # transient network
    "Connection refused",
    "rate limit",
    "Rate limit",
    "quota",
    "insufficient_quota",
    "no available channel",            # OrcaRouter no upstream configured
    "all channels failed",
    "channel quota",
    "model is not available",
    "only supported in v1/responses",  # gpt-5-pro endpoint mismatch (model itself wrong)
]


def classify_error(msg: str) -> str:
    """Return 'env' if error is user environment / upstream config, else 'plugin'."""
    lower = msg.lower()
    for sig in ENV_ERROR_SIGNALS:
        if sig.lower() in lower:
            return "env"
    return "plugin"


def probe_model(api_key: str, endpoint: str, model_id: str, body: dict, timeout: int = 300) -> tuple[str, str]:
    """Return (status, message) where status is 'pass' | 'fail_plugin' | 'warn_env'.

    Uses streaming since some upstreams (glm-4.5 etc.) require it. Reads the
    SSE stream just enough to confirm at least one data chunk arrived.
    """
    body = {**body, "stream": True}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
    }
    try:
        r = requests.post(
            f"{endpoint}/chat/completions",
            headers=headers,
            json=body,
            timeout=timeout,
            stream=True,
        )
    except requests.RequestException as e:
        msg = f"network error: {e}"
        return ("warn_env" if classify_error(msg) == "env" else "fail_plugin", msg)

    if r.status_code == 200:
        chunks_seen = 0
        try:
            for raw in r.iter_lines(decode_unicode=True):
                if not raw:
                    continue
                if raw.startswith("data:"):
                    payload = raw[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        json.loads(payload)
                        chunks_seen += 1
                        if chunks_seen >= 2:  # got real data
                            break
                    except json.JSONDecodeError:
                        continue
        finally:
            r.close()
        if chunks_seen == 0:
            return "fail_plugin", "200 but no SSE data chunks"
        return "pass", f"OK ({chunks_seen}+ stream chunks)"

    try:
        err = r.json()
        msg = err.get("error", {}).get("message") or json.dumps(err)[:200]
    except json.JSONDecodeError:
        msg = r.text[:200]
    full_msg = f"HTTP {r.status_code}: {msg}"
    return ("warn_env" if classify_error(msg) == "env" else "fail_plugin", full_msg)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--models", nargs="*", help="Limit to specific model IDs")
    parser.add_argument(
        "--endpoint",
        default=os.getenv("ORCAROUTER_API_BASE_URL", DEFAULT_ENDPOINT),
    )
    parser.add_argument("--sleep", type=float, default=0.5, help="Delay between calls")
    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="HTTP timeout per request in seconds (default 300; some reasoning models need this)",
    )
    args = parser.parse_args()

    api_key = os.getenv("ORCAROUTER_API_KEY")
    if not api_key:
        print("ERROR: ORCAROUTER_API_KEY env var required", file=sys.stderr)
        sys.exit(2)

    if args.models:
        targets = args.models
    else:
        position_file = LLM_DIR / "_position.yaml"
        targets = yaml.safe_load(position_file.read_text(encoding="utf-8")) or []

    print(f"Probing {len(targets)} models against {args.endpoint}\n")

    results = []
    for model_id in targets:
        if model_id == "orcarouter/auto":
            # AUTO router — exercise with no special params
            body = {
                "model": model_id,
                "messages": [{"role": "user", "content": "Reply with just 'ok'."}],
                "max_tokens": 10,
            }
        else:
            yaml_data = load_yaml(model_id)
            if not yaml_data:
                print(f"[SKIP] {model_id}: no YAML file")
                continue
            body = build_test_payload(model_id, yaml_data)

        status, msg = probe_model(api_key, args.endpoint, model_id, body, timeout=args.timeout)
        label = {"pass": "PASS", "fail_plugin": "FAIL", "warn_env": "WARN"}[status]
        print(f"[{label}] {model_id}: {msg}")
        results.append((model_id, status, msg))
        time.sleep(args.sleep)

    print()
    print("=" * 70)
    passed = sum(1 for _, s, _ in results if s == "pass")
    failed = sum(1 for _, s, _ in results if s == "fail_plugin")
    warned = sum(1 for _, s, _ in results if s == "warn_env")
    print(f"PASSED:           {passed} / {len(results)}")
    print(f"FAIL (plugin):    {failed}")
    print(f"WARN (env/infra): {warned}")
    if failed:
        print("\nReal plugin failures (suggest classification adjustment):")
        for model_id, s, msg in results:
            if s == "fail_plugin":
                print(f"  - {model_id}: {msg}")
    if warned:
        print("\nEnvironment / upstream issues (NOT plugin bugs):")
        for model_id, s, msg in results:
            if s == "warn_env":
                print(f"  - {model_id}: {msg}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()

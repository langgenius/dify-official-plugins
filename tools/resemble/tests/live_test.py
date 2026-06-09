"""Live API test harness for the Resemble Detect + Intelligence Dify plugin.

Exercises the SAME code the plugin runs (tools/resemble_api.py) against the real
API. Reads RESEMBLE_API_KEY from the project .env (../../../../.env) or the env.

Usage:
    python3 tests/live_test.py            # auth probe + tiny image detect
    python3 tests/live_test.py --full     # also watermark detect + intelligence
"""
import json
import os
import sys
from pathlib import Path

# Make tools/ importable when run from the plugin root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.resemble_api import (  # noqa: E402
    ResembleClient, ResembleError, build_detect_body, extract_uuid,
    summarize_detection, summarize_watermark_detect,
)

# Small, stable, public test media.
TEST_IMAGE = "https://www.gstatic.com/webp/gallery/1.jpg"


def load_env():
    # Walk up to find a .env with RESEMBLE_API_KEY.
    here = Path(__file__).resolve()
    for parent in here.parents:
        env = parent / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            break


def dump(label, data):
    print(f"\n===== {label} =====")
    print(json.dumps(data, indent=2)[:4000])


def main():
    load_env()
    key = os.environ.get("RESEMBLE_API_KEY")
    base = os.environ.get("RESEMBLE_BASE_URL")
    if not key:
        print("NO RESEMBLE_API_KEY found in env/.env"); sys.exit(2)
    print(f"Using base_url={base or 'default'} key=***{key[-4:]}")

    client = ResembleClient(api_key=key, base_url=base)

    # 1) Auth probe
    try:
        client.validate_key()
        print("\n[1] AUTH: key accepted (no 401/403).")
    except ResembleError as e:
        print(f"\n[1] AUTH FAILED: {e}")
        sys.exit(1)

    # 2) Submit a tiny image detection and inspect the RAW submit response shape.
    params = {"url": TEST_IMAGE, "model_types": "image"}
    body = build_detect_body(params)
    dump("detect POST body", body)
    try:
        submitted = client.request("POST", "/detect", json_body=body)
    except ResembleError as e:
        print(f"\n[2] DETECT SUBMIT FAILED: {e}")
        sys.exit(1)
    dump("detect POST response (raw)", submitted)
    uuid = extract_uuid(submitted)
    print(f"\n[2] extracted uuid = {uuid}")

    # 3) Poll to completion.
    if uuid:
        try:
            result = client.poll(f"/detect/{uuid}", max_wait_seconds=120)
            dump("detect GET result (raw)", result)
            print("\n[3] SUMMARY:\n" + summarize_detection(result))
        except ResembleError as e:
            print(f"\n[3] POLL FAILED: {e}")

    if "--full" in sys.argv:
        try:
            wm = client.request(
                "POST", "/watermark/detect",
                json_body={"url": TEST_IMAGE}, extra_headers={"Prefer": "wait"},
            )
            dump("watermark/detect response (raw)", wm)
            print("\n[4] " + summarize_watermark_detect(wm))
        except ResembleError as e:
            print(f"\n[4] WATERMARK DETECT FAILED: {e}")


if __name__ == "__main__":
    main()

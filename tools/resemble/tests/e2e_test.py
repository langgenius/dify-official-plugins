"""End-to-end live test: imports the REAL tool classes (via a lightweight
dify_plugin stub) and runs each tool's `_invoke` against the live Resemble API.

This is the highest-fidelity test short of the full Dify runtime — it exercises
the exact tool code that ships in the plugin.

Usage:
    python3 tests/e2e_test.py           # all 5 tools + provider validation, live
    python3 tests/e2e_test.py --no-apply  # skip watermark apply (saves credits)
"""
import json
import os
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEST_IMAGE = "https://www.gstatic.com/webp/gallery/1.jpg"
TEST_AUDIO = "https://samplelib.com/lib/preview/mp3/sample-3s.mp3"  # watermarking is audio-first


# --------------------------------------------------------------------------- #
# Install a minimal dify_plugin stub so the real tool modules import and run.
# --------------------------------------------------------------------------- #
def install_stub():
    dp = types.ModuleType("dify_plugin")

    class ToolInvokeMessage:
        def __init__(self, type, message):
            self.type = type
            self.message = message

    class Runtime:
        def __init__(self, credentials):
            self.credentials = credentials

    class Tool:
        def __init__(self, runtime=None, session=None):
            self.runtime = runtime
            self.session = session

        def create_json_message(self, data):
            return ToolInvokeMessage("json", data)

        def create_text_message(self, text):
            return ToolInvokeMessage("text", text)

    class ToolProvider:
        pass

    class DifyPluginEnv:
        def __init__(self, *a, **k):
            pass

    class Plugin:
        def __init__(self, *a, **k):
            pass

        def run(self):
            pass

    dp.Tool = Tool
    dp.ToolProvider = ToolProvider
    dp.DifyPluginEnv = DifyPluginEnv
    dp.Plugin = Plugin
    dp.Runtime = Runtime
    dp.ToolInvokeMessage = ToolInvokeMessage

    ent = types.ModuleType("dify_plugin.entities")
    ent_tool = types.ModuleType("dify_plugin.entities.tool")
    ent_tool.ToolInvokeMessage = ToolInvokeMessage
    err = types.ModuleType("dify_plugin.errors")
    err_tool = types.ModuleType("dify_plugin.errors.tool")

    class ToolProviderCredentialValidationError(Exception):
        pass

    err_tool.ToolProviderCredentialValidationError = ToolProviderCredentialValidationError

    sys.modules.update({
        "dify_plugin": dp,
        "dify_plugin.entities": ent,
        "dify_plugin.entities.tool": ent_tool,
        "dify_plugin.errors": err,
        "dify_plugin.errors.tool": err_tool,
    })
    return dp


def load_env():
    here = Path(__file__).resolve()
    for parent in here.parents:
        env = parent / ".env"
        if env.exists():
            for line in env.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            return


def show(msgs):
    """Print yielded ToolInvokeMessages; return the first json payload."""
    payload = None
    for m in msgs:
        if m.type == "json":
            payload = m.message
            blob = json.dumps(m.message, indent=2)
            print("  [json] " + (blob if len(blob) < 900 else blob[:900] + " …(truncated)"))
        else:
            print("  [text] " + str(m.message).replace("\n", "\n         "))
    return payload


def main():
    load_env()
    dp = install_stub()
    creds = {
        "resemble_api_key": os.environ.get("RESEMBLE_API_KEY"),
        "base_url": os.environ.get("RESEMBLE_BASE_URL"),
    }
    if not creds["resemble_api_key"]:
        print("NO RESEMBLE_API_KEY"); sys.exit(2)

    from provider.resemble import ResembleProvider
    from tools.detect import DetectTool
    from tools.detect_ask import DetectAskTool
    from tools.intelligence import IntelligenceTool
    from tools.watermark_apply import WatermarkApplyTool
    from tools.watermark_detect import WatermarkDetectTool

    results = {}

    def rt(cls):
        return cls(runtime=dp.Runtime(creds))

    watermark_only = "--watermark-only" in sys.argv

    if watermark_only:
        print("\n### watermark_detect (audio)")
        try:
            show(rt(WatermarkDetectTool)._invoke({"url": TEST_AUDIO}))
            results["watermark_detect"] = True
        except Exception as e:
            results["watermark_detect"] = False; print(f"  FAIL — {e}")
        print("\n### watermark_apply (audio)")
        try:
            show(rt(WatermarkApplyTool)._invoke(
                {"url": TEST_AUDIO, "custom_message": "resemble-test", "max_wait_seconds": 120}
            ))
            results["watermark_apply"] = True
        except Exception as e:
            results["watermark_apply"] = False; print(f"  FAIL — {e}")
        _summary(results); return

    # 0) Provider credential validation
    print("\n### [0] provider._validate_credentials")
    try:
        ResembleProvider()._validate_credentials(creds)
        print("  PASS — credentials accepted"); results["provider"] = True
    except Exception as e:
        print(f"  FAIL — {e}"); results["provider"] = False

    # 1) Deepfake detection (image)
    print("\n### [1] detect (image)")
    try:
        payload = show(rt(DetectTool)._invoke(
            {"url": TEST_IMAGE, "model_types": "image", "max_wait_seconds": 120}
        ))
        uuid = (payload or {}).get("item", {}).get("uuid") if payload else None
        results["detect"] = bool(uuid)
        print(f"  -> detect uuid = {uuid}")
    except Exception as e:
        uuid = None; results["detect"] = False; print(f"  FAIL — {e}")

    # 2) Ask about the detection (reuses the completed uuid)
    print("\n### [2] detect_ask")
    if uuid:
        try:
            show(rt(DetectAskTool)._invoke(
                {"detect_uuid": uuid,
                 "query": "In one sentence, is this image real or AI-generated and how confident?",
                 "max_wait_seconds": 120}
            ))
            results["detect_ask"] = True
        except Exception as e:
            results["detect_ask"] = False; print(f"  FAIL — {e}")
    else:
        print("  SKIP — no detect uuid"); results["detect_ask"] = None

    # 3) Standalone intelligence (image)
    print("\n### [3] intelligence (image)")
    try:
        show(rt(IntelligenceTool)._invoke(
            {"url": TEST_IMAGE, "media_type": "image", "structured_json": True,
             "max_wait_seconds": 120}
        ))
        results["intelligence"] = True
    except Exception as e:
        results["intelligence"] = False; print(f"  FAIL — {e}")

    # 4) Watermark detect (audio — watermarking is audio-first)
    print("\n### [4] watermark_detect (audio)")
    try:
        show(rt(WatermarkDetectTool)._invoke({"url": TEST_AUDIO}))
        results["watermark_detect"] = True
    except Exception as e:
        results["watermark_detect"] = False; print(f"  FAIL — {e}")

    # 5) Watermark apply (audio)
    if "--no-apply" not in sys.argv:
        print("\n### [5] watermark_apply (audio)")
        try:
            show(rt(WatermarkApplyTool)._invoke(
                {"url": TEST_AUDIO, "custom_message": "resemble-test", "max_wait_seconds": 120}
            ))
            results["watermark_apply"] = True
        except Exception as e:
            results["watermark_apply"] = False; print(f"  FAIL — {e}")

    _summary(results)


def _summary(results):
    print("\n================ SUMMARY ================")
    for k, v in results.items():
        mark = "PASS" if v else ("SKIP" if v is None else "FAIL")
        print(f"  {mark:4}  {k}")
    failed = [k for k, v in results.items() if v is False]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()

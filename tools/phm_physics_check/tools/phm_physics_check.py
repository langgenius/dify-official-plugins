import json
import sys
from pathlib import Path
from typing import Any, Dict, Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from phm_lite import full_check  # noqa: E402


class PhmPhysicsCheckTool(Tool):
    def _invoke(
        self, tool_parameters: Dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        text = str(tool_parameters.get("text") or "")
        if not text.strip():
            yield self.create_json_message(
                {
                    "verdict": "WARN",
                    "n_quantities_checked": 0,
                    "violations": [
                        {
                            "rule": "empty_input",
                            "severity": "WARN",
                            "detail": "No text provided; nothing to verify.",
                            "location": "",
                        }
                    ],
                    "engine": "PHM-Lite",
                    "deterministic": True,
                }
            )
            return

        kinematics = None
        raw_k = str(tool_parameters.get("kinematics_json") or "").strip()
        if raw_k:
            try:
                parsed = json.loads(raw_k)
                if isinstance(parsed, dict):
                    kinematics = {
                        k: float(v)
                        for k, v in parsed.items()
                        if k in ("v0", "v", "a", "t", "s", "h")
                    }
            except (ValueError, TypeError):
                pass  # malformed JSON is ignored deterministically

        result = full_check(text, kinematics=kinematics)
        yield self.create_json_message(result)

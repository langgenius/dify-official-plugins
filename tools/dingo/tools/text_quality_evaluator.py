from typing import Any, Dict, List, Union
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class TextQualityEvaluatorTool(Tool):
    """Evaluate text quality using Dingo if available, fallback gracefully otherwise."""

    def _invoke(self, user_id: str, tool_parameters: Dict[str, Any]) -> Union[ToolInvokeMessage, List[ToolInvokeMessage]]:
        text_content = (tool_parameters.get("text_content") or "").strip()
        rule_group = tool_parameters.get("rule_group", "default")
        if not text_content:
            return self.create_text_message("Error: Text content cannot be empty")

        # Try using dingo-python if installed
        try:
            from dingo.io.input import Data  # type: ignore
            from dingo.model.rule.rule_common import RuleEnterAndSpace, RuleContentNull  # type: ignore
        except Exception:
            # Fallback: minimal heuristic checks without dingo
            issues: List[str] = []
            if len(text_content) < 2:
                issues.append("Too short: content length < 2")
            if text_content.strip() == ":" or text_content.endswith(":"):
                issues.append("Ends with colon")
            if not any(ch.isalpha() for ch in text_content):
                issues.append("No alphabetic characters detected")

            score = int(round((1 - len(issues) / 3) * 100)) if issues else 100
            body = [
                "Text Quality Assessment Results (fallback mode):",
                f"Quality Score: {score}%",
                f"Issues Found: {len(issues)}",
            ]
            if issues:
                body.append("Detected Issues:")
                body.extend(f"- {i}" for i in issues)
            else:
                body.append("No obvious issues detected.")
            return self.create_text_message("\n".join(body))

        # Use dingo rules when available
        data = Data(data_id="dify_eval_001", content=text_content)
        rules = [RuleEnterAndSpace(), RuleContentNull()]
        issues: List[str] = []
        for rule in rules:
            try:
                result = rule.eval(data)
                if result.error_status:
                    issues.append(f"{result.name}: {result.reason[0] if result.reason else ''}")
            except Exception:
                continue

        total = max(len(rules), 1)
        score = int(round((1 - len(issues) / total) * 100))
        lines = [
            "Text Quality Assessment Results:",
            f"Quality Score: {score}%",
            f"Issues Found: {len(issues)}",
        ]
        if issues:
            lines.append("Detected Issues:")
            lines.extend(f"- {it}" for it in issues)
        else:
            lines.append("No quality issues detected with the selected rules.")
        return self.create_text_message("\n".join(lines))

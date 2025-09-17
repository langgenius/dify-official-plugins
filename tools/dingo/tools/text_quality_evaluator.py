from typing import Any, Dict, List, Generator
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class TextQualityEvaluatorTool(Tool):
    """Evaluate text quality using Dingo if available, fallback gracefully otherwise."""

    def _invoke(self, tool_parameters: Dict[str, Any] | None = None, *args, **kwargs) -> "Generator[ToolInvokeMessage, Any, Any]":
        # Backward-compatible handling for different SDK call conventions:
        # - New SDK: _invoke(tool_parameters)
        # - Old SDK: _invoke(user_id, tool_parameters) or even _invoke()
        if not isinstance(tool_parameters, dict) or not tool_parameters:
            # prefer explicit kw
            if isinstance(kwargs.get("tool_parameters"), dict):
                tool_parameters = kwargs["tool_parameters"]
            else:
                # search positional args for a dict
                for a in args or []:
                    if isinstance(a, dict):
                        tool_parameters = a
                        break
        if not isinstance(tool_parameters, dict):
            tool_parameters = {}

        text_content = (tool_parameters.get("text_content") or "").strip()
        rule_group = tool_parameters.get("rule_group", "default")
        if not text_content:
            yield self.create_text_message("Error: Text content cannot be empty")
            return

        # Try using dingo-python if installed
        try:
            import importlib
            import inspect
            import pkgutil
            from dingo.io.input import Data  # type: ignore
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
            yield self.create_text_message("\n".join(body))
            return

        # Dingo available: build registry of Rule* classes dynamically
        def _build_registry() -> Dict[str, Any]:
            try:
                base = "dingo.model.rule"
                pkg = importlib.import_module(base)
                reg: Dict[str, Any] = {}
                for _, mname, _ in pkgutil.walk_packages(pkg.__path__, base + "."):
                    try:
                        mod = importlib.import_module(mname)
                    except Exception:
                        continue
                    for cname, cls in inspect.getmembers(mod, inspect.isclass):
                        if cname.startswith("Rule") and hasattr(cls, "eval"):
                            reg[cname] = cls
                return reg
            except Exception:
                return {}

        registry = getattr(self, "_dingo_registry", None)
        if not isinstance(registry, dict) or not registry:
            registry = _build_registry()
            setattr(self, "_dingo_registry", registry)

        def _rules_from_group(group: str) -> List[Any]:
            # Minimal grouping: default set; other groups fallback to default for now
            mapping = {
                "default": ["RuleEnterAndSpace", "RuleContentNull"],
                "sft": ["RuleEnterAndSpace", "RuleContentNull"],
                "rag": ["RuleEnterAndSpace", "RuleContentNull"],
                "hallucination": ["RuleEnterAndSpace", "RuleContentNull"],
                "pretrain": ["RuleEnterAndSpace", "RuleContentNull"],
            }
            names = mapping.get(str(group).lower(), mapping["default"])
            return [registry[n]() for n in names if n in registry]

        selected = tool_parameters.get("rule_list") or []
        if isinstance(selected, str):
            selected = [x.strip() for x in selected.split(",") if x.strip()]
        rules: List[Any] = []
        if isinstance(selected, list) and selected:
            rules = [registry[n]() for n in selected if n in registry]
        if not rules:
            rules = _rules_from_group(rule_group)
        if not rules:
            # ultimate fallback to a sensible default if registry is empty
            rules = _rules_from_group("default")

        data = Data(data_id="dify_eval_001", content=text_content)
        issues: List[str] = []
        for rule in rules:
            try:
                result = rule.eval(data)
                if getattr(result, "error_status", False):
                    reason = ""
                    try:
                        reason = result.reason[0] if getattr(result, "reason", None) else ""
                    except Exception:
                        reason = ""
                    issues.append(f"{getattr(result, 'name', rule.__class__.__name__)}: {reason}")
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
        yield self.create_text_message("\n".join(lines))


class DingoTool(TextQualityEvaluatorTool):
    """Generic Dingo tool entrypoint.
    Currently implements text quality evaluation; future capabilities can extend this class
    while keeping backward compatibility with TextQualityEvaluatorTool name.
    """
    pass

__all__ = ["TextQualityEvaluatorTool", "DingoTool"]

from typing import Any, Dict, List, Union
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class TextQualityEvaluatorTool(Tool):
    """Evaluate text quality using Dingo if available, fallback gracefully otherwise."""

    def _get_rule_registry(self):
        """Build dynamic rule registry with backward compatibility."""
        try:
            # Try to import dingo rules based on actual available rules
            from dingo.model.rule import rule_common  # type: ignore

            # Start with basic rules that are most likely to exist
            registry = {
                "RuleEnterAndSpace": rule_common.RuleEnterAndSpace,
                "RuleContentNull": rule_common.RuleContentNull,
            }

            # Try to add other common rules
            common_rules = [
                "RuleColonEnd", "RuleDocRepeat", "RuleSpecialCharacter",
                "RuleAlphaWords", "RuleCapitalWords", "RuleContentLength",
                "RuleLanguageDetection", "RuleTextQuality", "RuleDataDiversity",
                "RuleCompleteness", "RuleRelevance", "RuleSimilarity"
            ]

            for rule_name in common_rules:
                try:
                    rule_class = getattr(rule_common, rule_name, None)
                    if rule_class:
                        registry[rule_name] = rule_class
                except AttributeError:
                    continue

            # Try to add hallucination rules
            try:
                from dingo.model.rule import rule_hallucination  # type: ignore
                if hasattr(rule_hallucination, 'RuleHallucinationHHEM'):
                    registry["RuleHallucinationHHEM"] = rule_hallucination.RuleHallucinationHHEM
            except ImportError:
                pass

            # Filter out rules that don't exist or can't be instantiated
            available_registry = {}
            for name, rule_class in registry.items():
                try:
                    # Test if rule class is actually available
                    rule_class()
                    available_registry[name] = rule_class
                except Exception:
                    continue

            return available_registry

        except ImportError:
            # Fallback to basic rules only
            try:
                from dingo.model.rule.rule_common import RuleEnterAndSpace, RuleContentNull  # type: ignore
                return {
                    "RuleEnterAndSpace": RuleEnterAndSpace,
                    "RuleContentNull": RuleContentNull,
                }
            except ImportError:
                return {}

    def _get_rules_for_group(self, rule_group: str, rule_list: List[str] = None):
        """Get rules based on group and optional specific rule list."""
        registry = self._get_rule_registry()

        if rule_list:
            # Use specific rules if provided
            rules = []
            for rule_name in rule_list:
                if rule_name in registry:
                    try:
                        rules.append(registry[rule_name]())
                    except Exception:
                        continue
            return rules

        # Use rule groups based on actual Dingo documentation
        group_mappings = {
            "default": ["RuleColonEnd", "RuleContentNull", "RuleDocRepeat", "RuleEnterAndSpace", "RuleSpecialCharacter"],
            "sft": ["RuleColonEnd", "RuleContentNull", "RuleDocRepeat", "RuleHallucinationHHEM"],
            "rag": ["RuleHallucinationHHEM", "RuleRelevance", "RuleContentNull"],
            "hallucination": ["RuleHallucinationHHEM"],
            "pretrain": ["RuleAlphaWords", "RuleCapitalWords", "RuleContentLength", "RuleLanguageDetection",
                        "RuleTextQuality", "RuleDataDiversity", "RuleCompleteness", "RuleSimilarity"],
        }

        rule_names = group_mappings.get(rule_group, group_mappings["default"])
        rules = []
        for rule_name in rule_names:
            if rule_name in registry:
                try:
                    rules.append(registry[rule_name]())
                except Exception:
                    continue

        return rules

    def _invoke(self, user_id: str, tool_parameters: Dict[str, Any]) -> Union[ToolInvokeMessage, List[ToolInvokeMessage]]:
        text_content = (tool_parameters.get("text_content") or "").strip()
        rule_group = tool_parameters.get("rule_group", "default")
        rule_list = tool_parameters.get("rule_list", [])

        if not text_content:
            return self.create_text_message("Error: Text content cannot be empty")

        # Try using dingo-python if installed
        try:
            from dingo.io.input import Data  # type: ignore

            # Get rules based on parameters
            rules = self._get_rules_for_group(rule_group, rule_list)

            if not rules:
                # Fallback to basic rules if no rules available
                from dingo.model.rule.rule_common import RuleEnterAndSpace, RuleContentNull  # type: ignore
                rules = [RuleEnterAndSpace(), RuleContentNull()]

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
        issues: List[str] = []
        rule_names_used = []

        for rule in rules:
            try:
                result = rule.eval(data)
                rule_names_used.append(rule.__class__.__name__)
                if result.error_status:
                    reason = result.reason[0] if result.reason else "Quality issue detected"
                    issues.append(f"{result.name}: {reason}")
            except Exception as e:
                # Continue with other rules if one fails
                continue

        total = max(len(rule_names_used), 1)
        score = int(round((1 - len(issues) / total) * 100))

        # Build comprehensive result message
        lines = [
            "Text Quality Assessment Results:",
            f"Quality Score: {score}%",
            f"Rules Applied: {len(rule_names_used)} ({', '.join(rule_names_used)})",
            f"Issues Found: {len(issues)}",
        ]

        if issues:
            lines.append("\nDetected Issues:")
            lines.extend(f"- {issue}" for issue in issues)
        else:
            lines.append("\nNo quality issues detected with the selected rules.")

        # Add recommendations based on score
        if score < 50:
            lines.append("\n⚠️ Recommendation: Significant quality issues detected. Consider revising the content.")
        elif score < 80:
            lines.append("\n💡 Recommendation: Minor quality issues detected. Review and improve where possible.")
        else:
            lines.append("\n✅ Recommendation: Good quality content. No major issues detected.")

        return self.create_text_message("\n".join(lines))

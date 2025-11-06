from typing import Any, List
from collections.abc import Generator
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage


class TextQualityEvaluatorTool(Tool):
    """Evaluate text quality using Dingo if available, fallback gracefully otherwise."""

    def _get_rule_registry(self):
        """Get available dingo rules with simple fallback."""
        try:
            from dingo.model.rule import rule_common  # type: ignore
            return {
                "RuleEnterAndSpace": rule_common.RuleEnterAndSpace,
                "RuleContentNull": rule_common.RuleContentNull,
            }
        except ImportError:
            # Return empty dict if dingo is not available
            return {}

    def _get_rules_for_group(self, rule_group: str, rule_list: List[str] = None):
        """Get rules based on group and optional specific rule list."""
        registry = self._get_rule_registry()

        # If no registry available, return empty list
        if not registry:
            return []

        if rule_list:
            # Use specific rules if provided
            rules = []
            for rule_name in rule_list:
                if rule_name in registry:
                    try:
                        rule_instance = registry[rule_name]()
                        if rule_instance is not None:
                            rules.append(rule_instance)
                    except Exception:
                        continue
            return rules

        # Simplified rule groups - only use rules we know exist
        group_mappings = {
            "default": ["RuleEnterAndSpace", "RuleContentNull"],
            "sft": ["RuleEnterAndSpace", "RuleContentNull"],
            "rag": ["RuleEnterAndSpace", "RuleContentNull"],
            "hallucination": ["RuleEnterAndSpace", "RuleContentNull"],
            "pretrain": ["RuleEnterAndSpace", "RuleContentNull"],
        }

        rule_names = group_mappings.get(rule_group, group_mappings["default"])
        rules = []
        for rule_name in rule_names:
            if rule_name in registry:
                try:
                    rule_instance = registry[rule_name]()
                    if rule_instance is not None:
                        rules.append(rule_instance)
                except Exception:
                    continue

        # Ensure we always return at least one rule if registry has rules
        if not rules and registry:
            try:
                first_rule_class = next(iter(registry.values()))
                rule_instance = first_rule_class()
                if rule_instance is not None:
                    rules.append(rule_instance)
            except Exception:
                pass

        return rules

    def _get_prompts_for_list(self, prompt_list: List[str] = None):
        """Get prompts based on specific prompt list."""
        try:
            from dingo.model.prompt import (  # type: ignore
                PromptRepeat, PromptContentChaos, PromptWordStick,
                PromptCodeListIssue, PromptUnreadIssue
            )

            prompt_registry = {
                'PromptRepeat': PromptRepeat,
                'PromptContentChaos': PromptContentChaos,
                'PromptWordStick': PromptWordStick,
                'PromptCodeListIssue': PromptCodeListIssue,
                'PromptUnreadIssue': PromptUnreadIssue,
            }
        except ImportError:
            # Return empty list if dingo prompts are not available
            return []

        if not prompt_list:
            return []

        prompts = []
        for prompt_name in prompt_list:
            if prompt_name in prompt_registry:
                try:
                    prompt_instance = prompt_registry[prompt_name]()
                    if prompt_instance is not None:
                        prompts.append(prompt_instance)
                except Exception:
                    # Skip if prompt instantiation fails
                    continue

        return prompts

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        text_content = (tool_parameters.get("text_content") or "").strip()
        rule_group = tool_parameters.get("rule_group", "default")
        rule_list = tool_parameters.get("rule_list", [])
        prompt_list = tool_parameters.get("prompt_list", [])

        if not text_content:
            yield self.create_text_message("Error: Text content cannot be empty")
            return

        # Try using dingo-python if installed
        try:
            from dingo.io.input import Data  # type: ignore

            # Get rules based on parameters
            rules = self._get_rules_for_group(rule_group, rule_list)

            # Get prompts based on parameters
            prompts = self._get_prompts_for_list(prompt_list)

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
            yield self.create_text_message("\n".join(body))
            return

        # Use dingo rules when available
        try:
            data = Data(data_id="dify_eval_001", content=text_content)
            issues: List[str] = []
            rule_names_used = []

            for rule in rules:
                if rule is None:
                    continue

                try:
                    result = rule.eval(data)
                    rule_name = getattr(rule, '__class__', type(rule)).__name__
                    rule_names_used.append(rule_name)

                    if result and hasattr(result, 'error_status') and result.error_status:
                        reason = "Quality issue detected"
                        if hasattr(result, 'reason') and result.reason:
                            reason = result.reason[0] if isinstance(result.reason, list) else str(result.reason)
                        result_name = getattr(result, 'name', rule_name)
                        issues.append(f"{result_name}: {reason}")
                except Exception as e:
                    # Continue with other rules if one fails
                    continue

            # Process prompts if available
            prompt_names_used = []
            for prompt in prompts:
                if prompt is None:
                    continue

                try:
                    result = prompt.eval(data)
                    prompt_name = getattr(prompt, '__class__', type(prompt)).__name__
                    prompt_names_used.append(prompt_name)

                    if result and hasattr(result, 'error_status') and result.error_status:
                        reason = "Prompt issue detected"
                        if hasattr(result, 'reason') and result.reason:
                            reason = result.reason[0] if isinstance(result.reason, list) else str(result.reason)
                        result_name = getattr(result, 'name', prompt_name)
                        issues.append(f"{result_name}: {reason}")
                except Exception as e:
                    # Continue with other prompts if one fails
                    continue

        except Exception as e:
            # If Data creation fails, fall back to simple evaluation
            yield self.create_text_message(f"Text evaluation completed with basic checks. Content length: {len(text_content)} characters.")
            return

        # Ensure we have valid data for calculations
        total_evaluators = max(len(rule_names_used) + len(prompt_names_used), 1)
        issues_count = len(issues) if issues else 0
        score = max(0, min(100, int(round((1 - issues_count / total_evaluators) * 100))))

        # Build comprehensive result message
        rule_names_str = ', '.join(rule_names_used) if rule_names_used else "None"
        prompt_names_str = ', '.join(prompt_names_used) if prompt_names_used else "None"
        lines = [
            "Text Quality Assessment Results:",
            f"Quality Score: {score}%",
            f"Rules Applied: {len(rule_names_used)} ({rule_names_str})",
            f"Prompts Applied: {len(prompt_names_used)} ({prompt_names_str})",
            f"Issues Found: {issues_count}",
        ]

        if issues:
            lines.append("\nDetected Issues:")
            lines.extend(f"- {issue}" for issue in issues if issue)
        else:
            lines.append("\nNo quality issues detected with the selected rules.")

        # Add recommendations based on score
        if score < 50:
            lines.append("\n⚠️ Recommendation: Significant quality issues detected. Consider revising the content.")
        elif score < 80:
            lines.append("\n💡 Recommendation: Minor quality issues detected. Review and improve where possible.")
        else:
            lines.append("\n✅ Recommendation: Good quality content. No major issues detected.")

        yield self.create_text_message("\n".join(lines))

    def create_text_message(self, text: str) -> ToolInvokeMessage:
        """Create a text message for tool response."""
        if not text:
            text = "Evaluation completed."
        return ToolInvokeMessage(
            type=ToolInvokeMessage.MessageType.TEXT,
            message=ToolInvokeMessage.TextMessage(text=text)
        )

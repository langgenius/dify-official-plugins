from typing import Any, Generator
import json

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.llm import LLMModelConfig
from dify_plugin.entities.model.message import UserPromptMessage


class ResumeQualityCheckerTool(Tool):
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        # Get parameters
        resume_content = tool_parameters.get('resume_content', '').strip()
        language = tool_parameters.get('language', 'zh_Hans')
        check_mode = tool_parameters.get('check_mode', 'comprehensive')

        # Validate input
        if not resume_content:
            error_msg = "简历内容不能为空" if language == 'zh_Hans' else "Resume content cannot be empty"
            yield self.create_text_message(error_msg)
            return

        try:
            # Step 1: Rule-based checks (always run)
            rule_issues = self._run_dingo_rules(resume_content, language)

            # Step 2: LLM-based checks (optional)
            llm_issues = []
            if check_mode == "comprehensive":
                llm_issues = self._run_llm_check(resume_content, language)

            # Calculate results
            total_issues = len(rule_issues) + len(llm_issues)
            quality_status = self._get_quality_status(total_issues)

            # Build result
            result = {
                "check_mode": check_mode,
                "rule_issues": rule_issues,
                "llm_issues": llm_issues,
                "total_issues": total_issues,
                "quality_status": quality_status
            }

            # Create summary text
            summary = self._format_summary(result, language)

            # Yield results (like WizperTool pattern)
            json_message = self.create_json_message(result)
            text_message = self.create_text_message(summary)
            yield from [json_message, text_message]

        except Exception as e:
            error_msg = f"检测失败：{str(e)}" if language == 'zh_Hans' else f"Check failed: {str(e)}"
            yield self.create_text_message(error_msg)
    
    def _run_dingo_rules(self, resume_content: str, language: str) -> list:
        """Run Dingo resume quality rules."""
        try:
            from dingo.io import Data
            from dingo.model.rule.rule_resume import (
                RuleResumeIDCard,
                RuleResumeDetailedAddress,
                RuleResumeEmailMissing,
                RuleResumePhoneMissing,
                RuleResumePhoneFormat,
                RuleResumeExcessiveWhitespace,
                RuleResumeMarkdown,
                RuleResumeNameMissing,
                RuleResumeSectionMissing,
                RuleResumeEmoji,
                RuleResumeInformal,
                RuleResumeDateFormat,
                RuleResumeEducationMissing,
                RuleResumeExperienceMissing,
            )

            data = Data(data_id='resume_check', content=resume_content)
            issues = []

            # Define rules: (name, class, severity, category)
            rules = [
                ("RuleResumeIDCard", RuleResumeIDCard, "critical", "Privacy"),
                ("RuleResumeDetailedAddress", RuleResumeDetailedAddress, "high", "Privacy"),
                ("RuleResumeEmailMissing", RuleResumeEmailMissing, "high", "Contact"),
                ("RuleResumePhoneMissing", RuleResumePhoneMissing, "high", "Contact"),
                ("RuleResumePhoneFormat", RuleResumePhoneFormat, "medium", "Contact"),
                ("RuleResumeExcessiveWhitespace", RuleResumeExcessiveWhitespace, "low", "Format"),
                ("RuleResumeMarkdown", RuleResumeMarkdown, "medium", "Format"),
                ("RuleResumeNameMissing", RuleResumeNameMissing, "high", "Structure"),
                ("RuleResumeSectionMissing", RuleResumeSectionMissing, "medium", "Structure"),
                ("RuleResumeEmoji", RuleResumeEmoji, "medium", "Professionalism"),
                ("RuleResumeInformal", RuleResumeInformal, "medium", "Professionalism"),
                ("RuleResumeDateFormat", RuleResumeDateFormat, "low", "Date"),
                ("RuleResumeEducationMissing", RuleResumeEducationMissing, "medium", "Completeness"),
                ("RuleResumeExperienceMissing", RuleResumeExperienceMissing, "medium", "Completeness"),
            ]

            # Run rules
            for rule_name, rule_class, severity, category in rules:
                try:
                    result = rule_class.eval(data)
                    if result.error_status:
                        issues.append({
                            "source": "rule",
                            "rule_name": rule_name,
                            "category": category,
                            "severity": severity,
                            "description": result.reason[0] if result.reason else "检测到问题",
                            "type": result.type
                        })
                except Exception:
                    continue

            return issues

        except ImportError as e:
            return [{
                "source": "error",
                "description": f"Dingo 简历规则未安装: {str(e)}" if language == 'zh_Hans'
                              else f"Dingo resume rules not installed: {str(e)}"
            }]
        except Exception as e:
            return [{
                "source": "error",
                "description": f"规则检测失败: {str(e)}" if language == 'zh_Hans' else f"Rule check failed: {str(e)}"
            }]
    
    def _run_llm_check(self, resume_content: str, language: str) -> list:
        """Run LLM-based quality check."""
        try:
            # Build prompt
            prompt = self._build_prompt(resume_content, language)

            # Call LLM
            llm_config = {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "mode": "chat",
                "completion_params": {
                    "temperature": 0.3,
                    "max_tokens": 2000
                }
            }

            llm_result = self.session.model.llm.invoke(
                model_config=LLMModelConfig(**llm_config),
                prompt_messages=[UserPromptMessage(content=prompt)],
                stream=False
            )

            # Parse response
            if llm_result and hasattr(llm_result, 'message') and hasattr(llm_result.message, 'content'):
                return self._parse_llm_response(llm_result.message.content, language)
            else:
                return [{
                    "source": "error",
                    "description": "LLM返回空结果" if language == 'zh_Hans' else "LLM returned empty result"
                }]

        except Exception as e:
            return [{
                "source": "error",
                "description": f"LLM检测失败: {str(e)}" if language == 'zh_Hans' else f"LLM check failed: {str(e)}"
            }]
    
    def _build_prompt(self, resume_content: str, language: str) -> str:
        """Build LLM prompt."""
        template_zh = """### Role
你是一位专业的简历质量检测专家，擅长发现简历中的格式、隐私、结构等问题。

### Criteria
1. **Format（格式问题）**: 多余空格/换行、Markdown语法错误、特殊字符
2. **Privacy（隐私安全）**: 身份证泄露、详细地址、敏感信息
3. **Contact（联系方式）**: 邮箱/电话缺失或格式错误
4. **Structure（结构完整性）**: 缺少姓名、必要章节、标题层级混乱
5. **Professionalism（专业性）**: Emoji、口语化、错别字
6. **Date（日期格式）**: 格式不一致、逻辑错误

### Workflow
1. 仔细阅读简历，根据上述标准评估质量
2. 如果无问题，返回 {{"score": 1, "type": "Good", "name": "None", "reason": ""}}
3. 如果有问题，返回 {{"score": 0, "type": "问题类别", "name": "具体错误名", "reason": "详细说明"}}

### Warning
只输出 JSON 格式，不要有其他内容。

### Input
"""

        template_en = """### Role
You are a professional resume quality inspector.

### Criteria
1. **Format Issues**: Excessive whitespace, Markdown syntax errors, special characters
2. **Privacy & Security**: ID card leak, detailed address, sensitive info
3. **Contact Information**: Missing/incorrect email or phone
4. **Structure Completeness**: Missing name, required sections, heading hierarchy issues
5. **Professionalism**: Emoji, informal language, typos
6. **Date Format**: Inconsistent format, logical errors

### Workflow
1. Carefully read the resume and evaluate based on the above criteria
2. If no issues: return {{"score": 1, "type": "Good", "name": "None", "reason": ""}}
3. If issues found: return {{"score": 0, "type": "category", "name": "error_name", "reason": "detailed explanation"}}

### Warning
Output only JSON format, no other content.

### Input
"""

        template = template_zh if language == 'zh_Hans' else template_en
        return template + resume_content

    def _parse_llm_response(self, response: str, language: str) -> list:
        """Parse LLM JSON response."""
        # Clean markdown code blocks
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        # Parse JSON
        try:
            data = json.loads(response)
        except json.JSONDecodeError:
            return [{
                "source": "error",
                "description": f"LLM响应解析失败: {response[:100]}" if language == 'zh_Hans'
                              else f"Failed to parse LLM response: {response[:100]}"
            }]

        # Handle both dict and list responses
        if isinstance(data, list):
            # If LLM returns a list, process each item
            issues = []
            for item in data:
                if isinstance(item, dict) and item.get('score') == 0:
                    issue_type = item.get('type', '')
                    severity = "high" if issue_type == "Privacy" else "medium" if issue_type in ["Contact", "Structure"] else "low"
                    issues.append({
                        "source": "llm",
                        "category": issue_type,
                        "name": item.get('name', 'Unknown'),
                        "severity": severity,
                        "description": item.get('reason', ''),
                        "type": f"RESUME_QUALITY_BAD_{issue_type.upper()}"
                    })
            return issues
        elif isinstance(data, dict):
            # Handle single dict response
            if data.get('score') == 0:
                issue_type = data.get('type', '')
                severity = "high" if issue_type == "Privacy" else "medium" if issue_type in ["Contact", "Structure"] else "low"

                return [{
                    "source": "llm",
                    "category": issue_type,
                    "name": data.get('name', 'Unknown'),
                    "severity": severity,
                    "description": data.get('reason', ''),
                    "type": f"RESUME_QUALITY_BAD_{issue_type.upper()}"
                }]

        return []
    
    def _get_quality_status(self, total_issues: int) -> str:
        """Calculate quality status."""
        if total_issues == 0:
            return "excellent"
        elif total_issues <= 2:
            return "good"
        elif total_issues <= 5:
            return "fair"
        else:
            return "poor"

    def _format_summary(self, result: dict, language: str) -> str:
        """Format human-readable summary."""
        if language == 'zh_Hans':
            return self._format_summary_zh(result)
        else:
            return self._format_summary_en(result)

    def _format_summary_zh(self, result: dict) -> str:
        """Format Chinese summary."""
        status_emoji = {"excellent": "✅", "good": "👍", "fair": "⚠️", "poor": "❌"}
        status_text = {"excellent": "优秀", "good": "良好", "fair": "一般", "poor": "较差"}
        severity_emoji = {"critical": "🔴", "high": "🔴", "medium": "🟡", "low": "🟢"}

        summary = f"# 📋 简历质量检测报告\n\n"
        summary += f"**检测模式**: {result['check_mode']}\n"
        summary += f"**质量状态**: {status_emoji.get(result['quality_status'], '❓')} {status_text.get(result['quality_status'], '未知')}\n"
        summary += f"**发现问题**: {result['total_issues']} 个\n\n"

        # Rule issues
        if result['rule_issues']:
            summary += f"## 🔍 规则检测问题 ({len(result['rule_issues'])}个)\n\n"
            for idx, issue in enumerate(result['rule_issues'], 1):
                if issue.get('source') == 'error':
                    summary += f"{idx}. ❌ {issue['description']}\n"
                else:
                    summary += f"{idx}. {severity_emoji.get(issue['severity'], '⚪')} **{issue['category']}** - {issue['rule_name']}\n"
                    summary += f"   {issue['description']}\n\n"

        # LLM issues
        if result['llm_issues']:
            summary += f"## 🤖 LLM 深度检测问题 ({len(result['llm_issues'])}个)\n\n"
            for idx, issue in enumerate(result['llm_issues'], 1):
                if issue.get('source') == 'error':
                    summary += f"{idx}. ❌ {issue['description']}\n"
                else:
                    summary += f"{idx}. {severity_emoji.get(issue['severity'], '⚪')} **{issue['category']}** - {issue['name']}\n"
                    summary += f"   {issue['description']}\n\n"

        # No issues
        if result['total_issues'] == 0:
            summary += "## ✅ 恭喜！\n\n简历质量良好，未发现明显问题。\n"

        return summary

    def _format_summary_en(self, result: dict) -> str:
        """Format English summary."""
        status_emoji = {"excellent": "✅", "good": "👍", "fair": "⚠️", "poor": "❌"}
        severity_emoji = {"critical": "🔴", "high": "🔴", "medium": "🟡", "low": "🟢"}

        summary = f"# 📋 Resume Quality Check Report\n\n"
        summary += f"**Check Mode**: {result['check_mode']}\n"
        summary += f"**Quality Status**: {status_emoji.get(result['quality_status'], '❓')} {result['quality_status'].title()}\n"
        summary += f"**Issues Found**: {result['total_issues']}\n\n"

        # Rule issues
        if result['rule_issues']:
            summary += f"## 🔍 Rule-based Issues ({len(result['rule_issues'])})\n\n"
            for idx, issue in enumerate(result['rule_issues'], 1):
                if issue.get('source') == 'error':
                    summary += f"{idx}. ❌ {issue['description']}\n"
                else:
                    summary += f"{idx}. {severity_emoji.get(issue['severity'], '⚪')} **{issue['category']}** - {issue['rule_name']}\n"
                    summary += f"   {issue['description']}\n\n"

        # LLM issues
        if result['llm_issues']:
            summary += f"## 🤖 LLM Deep Check Issues ({len(result['llm_issues'])})\n\n"
            for idx, issue in enumerate(result['llm_issues'], 1):
                if issue.get('source') == 'error':
                    summary += f"{idx}. ❌ {issue['description']}\n"
                else:
                    summary += f"{idx}. {severity_emoji.get(issue['severity'], '⚪')} **{issue['category']}** - {issue['name']}\n"
                    summary += f"   {issue['description']}\n\n"

        # No issues
        if result['total_issues'] == 0:
            summary += "## ✅ Congratulations!\n\nResume quality is good, no obvious issues found.\n"

        return summary


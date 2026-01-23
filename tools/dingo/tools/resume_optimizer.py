"""
Resume Optimizer Tool - ATS-Focused Resume Optimization

This tool provides two modes:
1. Targeted Mode: When match_report is provided, injects missing keywords and de-emphasizes negative keywords.
2. General Mode: When match_report is empty, focuses on STAR polish and date unification only.

Features:
- Keyword injection (Force inject, Associative inject, Implied skills)
- Negative keyword de-emphasis
- Implicit STAR method polishing
- Silent date format unification (YYYY.MM–YYYY.MM)
- HTML separator conversion (<hr> → ---)
- Bilingual support (zh_Hans, en_US)
- No emoji policy for professional output
"""

from typing import Any
from collections.abc import Generator
import json
import traceback

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.llm import LLMModelConfig
from dify_plugin.entities.model.message import SystemPromptMessage, UserPromptMessage


class ResumeOptimizerTool(Tool):
    """
    ATS-focused resume optimization tool with dual-mode support.

    Targeted Mode: Keyword injection + De-emphasis + STAR polish (when match_report provided)
    General Mode: STAR polish + Format unification only (when match_report empty)
    """

    # ========== Localization Headers (NO EMOJI) ==========
    def _get_output_template_headers(self, language: str) -> dict:
        """
        Returns localized headers for the output report.
        STRICTLY NO EMOJIS in any of the values.
        """
        if language == 'zh_Hans':
            return {
                'report_title': 'ATS 优化报告',
                'disclaimer': '以下建议假设您确实具备相关技能，请核实准确性。',
                'strategy_title': '优化策略',
                'added_label': '高优先级关键词 (已添加)',
                'associative_label': '关联注入',
                'de_emphasized_label': '已弱化',
                'unused_label': '未能融入的建议',
                'all_matched_text': '所有核心关键词已匹配！',
                'sections_title': '板块优化对比',
                'before_label': '修改前',
                'after_label': '修改后',
                'changes_label': '变更说明',
                'no_changes_text': '*(无修改)*',
                'general_mode_note': '通用优化模式：未提供职位分析，仅进行 STAR 润色和格式统一。',
                'parse_warning': '警告：match_report 解析失败，已切换为通用模式。',
            }
        else:  # en_US
            return {
                'report_title': 'ATS Optimization Report',
                'disclaimer': 'Suggestions assume you possess these skills. Please verify accuracy.',
                'strategy_title': 'Strategy',
                'added_label': 'High Priority Keywords (Added)',
                'associative_label': 'Associative Injection',
                'de_emphasized_label': 'De-emphasized',
                'unused_label': 'Unused Suggestions',
                'all_matched_text': 'All core keywords matched!',
                'sections_title': 'Section Rewrites',
                'before_label': 'Before',
                'after_label': 'After',
                'changes_label': 'Changes',
                'no_changes_text': '*(No changes made)*',
                'general_mode_note': 'General Mode: Optimizing for clarity and STAR method (No JD provided).',
                'parse_warning': 'Warning: Failed to parse match_report, switched to General Mode.',
            }

    # ========== Parse match_report JSON ==========
    def _parse_match_report(self, match_report: str | dict | None) -> tuple[list, list, list, bool]:
        """
        Parse the match_report from KeywordMatcher.

        Args:
            match_report: JSON string or dict from KeywordMatcher

        Returns:
            tuple: (missing_required, missing_nice, negative_keywords, parse_success)
        """
        missing_required = []
        missing_nice = []
        negative_keywords = []

        if not match_report:
            return missing_required, missing_nice, negative_keywords, True  # Empty is valid (General Mode)

        try:
            # Parse JSON string if needed
            if isinstance(match_report, str):
                match_report = json.loads(match_report)

            # Extract from match_details structure
            match_details = match_report.get('match_details', {})

            # Extract missing keywords
            missing_list = match_details.get('missing', [])
            for item in missing_list:
                skill = item.get('skill', '')
                importance = item.get('importance', 'Nice-to-have')
                if skill:
                    if importance == 'Required':
                        missing_required.append(skill)
                    else:
                        missing_nice.append(skill)

            # Extract negative warnings
            negative_list = match_details.get('negative_warnings', [])
            for item in negative_list:
                skill = item.get('skill', '')
                if skill:
                    negative_keywords.append(skill)

            return missing_required, missing_nice, negative_keywords, True

        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            print(f"[resume_optimizer] Failed to parse match_report: {e}")
            return [], [], [], False

    # ========== Build Strategic Context Section (v0.6.0) ==========
    def _build_strategic_context_section(self, strategy_context: dict | str | None, language: str) -> str:
        """
        Build strategic context section from Dingo Scout output.

        Args:
            strategy_context: JSON string or dict from Dingo Scout
            language: 'zh_Hans' or 'en_US'

        Returns:
            Strategic context section string to inject into prompt
        """
        if not strategy_context:
            return ""

        try:
            # Parse if string
            if isinstance(strategy_context, str):
                strategy_context = json.loads(strategy_context)

            context = strategy_context.get('strategy_context', {})
            target_companies = context.get('target_companies', [])

            if not target_companies:
                return ""

            # Use first target company for tone adaptation
            company = target_companies[0]
            financial_status = company.get('financial_status', 'stable')
            company_name = company.get('name', '')
            interview_tips = company.get('interview_prep_tips', [])
            salary_leverage = company.get('salary_leverage', '')

            if language == 'zh_Hans':
                section = f"""
## 战略上下文 (来自 Dingo Scout)

**目标公司**: {company_name}
**财务状态**: {financial_status}

### 语气适配规则

"""
                if financial_status == "expansion":
                    section += """**扩张期公司** - 强调以下风格：
- 使用"快速迭代"、"从0到1"、"落地"等词汇
- 突出项目的交付速度和执行力
- 强调"主导"、"搭建"、"推动"等动词
- 增加量化数据（处理量、提升比例、上线时间）
"""
                elif financial_status == "stable":
                    section += """**稳健期公司** - 强调以下风格：
- 使用"规范化"、"优化"、"体系化"等词汇
- 突出流程改进和效率提升
- 强调"维护"、"改进"、"重构"等动词
- 增加稳定性指标（SLA、可用率、测试覆盖）
"""
                else:
                    section += "**标准风格** - 平衡增长与稳定的描述。\n"

                if interview_tips:
                    section += "\n### 面试准备建议\n"
                    for tip in interview_tips[:3]:
                        section += f"- {tip}\n"

                if salary_leverage:
                    section += f"\n### 薪资谈判背景\n{salary_leverage}\n"

            else:  # en_US
                section = f"""
## Strategic Context (from Dingo Scout)

**Target Company**: {company_name}
**Financial Status**: {financial_status}

### Tone Adaptation Rules

"""
                if financial_status == "expansion":
                    section += """**Expansion-phase Company** - Emphasize:
- Use terms like "fast iteration", "0 to 1", "deliver"
- Highlight delivery speed and execution
- Use action verbs: "led", "built", "drove"
- Add quantified data (volume, improvement %, launch time)
"""
                elif financial_status == "stable":
                    section += """**Stable-phase Company** - Emphasize:
- Use terms like "standardized", "optimized", "systematized"
- Highlight process improvements and efficiency gains
- Use action verbs: "maintained", "improved", "refactored"
- Add stability metrics (SLA, uptime, test coverage)
"""
                else:
                    section += "**Standard Style** - Balance growth and stability descriptions.\n"

                if interview_tips:
                    section += "\n### Interview Prep Tips\n"
                    for tip in interview_tips[:3]:
                        section += f"- {tip}\n"

                if salary_leverage:
                    section += f"\n### Salary Negotiation Context\n{salary_leverage}\n"

            return section

        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            print(f"[resume_optimizer] Failed to parse strategy_context: {e}")
            return ""

    # ========== Build System Prompt ==========
    def _build_system_prompt(
        self,
        language: str,
        target_position: str,
        missing_required: list,
        missing_nice: list,
        negative_keywords: list,
        is_targeted_mode: bool,
        parse_failed: bool = False,
        strategy_context: dict | str | None = None
    ) -> str:
        """
        Build the system prompt for LLM based on mode.

        Args:
            language: 'zh_Hans' or 'en_US'
            target_position: Target job position
            missing_required: List of required missing keywords
            missing_nice: List of nice-to-have missing keywords
            negative_keywords: List of negative keywords to de-emphasize
            is_targeted_mode: True if match_report provided
            parse_failed: True if match_report parsing failed
            strategy_context: Optional strategic context from Dingo Scout (v0.6.0)

        Returns:
            System prompt string
        """
        headers = self._get_output_template_headers(language)

        # Format keyword lists
        required_str = ', '.join(missing_required) if missing_required else 'None'
        nice_str = ', '.join(missing_nice) if missing_nice else 'None'
        negative_str = ', '.join(negative_keywords) if negative_keywords else 'None'

        # Build strategic context section (v0.6.0)
        strategic_section = self._build_strategic_context_section(strategy_context, language)

        if language == 'zh_Hans':
            return self._build_chinese_prompt(
                headers, target_position, required_str, nice_str, negative_str,
                is_targeted_mode, parse_failed, strategic_section
            )
        else:
            return self._build_english_prompt(
                headers, target_position, required_str, nice_str, negative_str,
                is_targeted_mode, parse_failed, strategic_section
            )

    def _build_chinese_prompt(
        self, headers: dict, target_position: str,
        required_str: str, nice_str: str, negative_str: str,
        is_targeted_mode: bool, parse_failed: bool,
        strategic_section: str = ""
    ) -> str:
        """Build Chinese system prompt."""
        base_prompt = f"""你是一位专业的 ATS（求职跟踪系统）优化专家。

## 重要规则
- **禁止使用任何 Emoji 符号**。输出必须是纯文本 Markdown。
- 简历内容保持原语言，不要翻译。
- 只输出有修改的板块，未修改的板块写 "{headers['no_changes_text']}"。
- "修改前"和"修改后"都必须输出该板块的**完整文本**，方便用户直接复制替换。

## 格式统一（静默修复）
1. **日期格式**：统一为 `YYYY.MM–YYYY.MM`（使用 Em dash，无空格）。删除"入学"等多余文字。
2. **分隔符**：将 HTML `<hr>` 或 `<hr class="...">` 转换为 Markdown `---`。
3. 在"变更说明"中简要提及这些格式统一操作。

## 润色方法
使用**隐式 STAR 法则**改善弱句：
- 不要使用 [Situation]、[Task] 等显式标签
- 用自然、专业的语言，让句子遵循"背景 → 任务 → 行动 → 结果"的逻辑流
"""

        if is_targeted_mode:
            mode_section = f"""
## 优化模式：针对性优化

目标岗位：{target_position}

### 关键词注入策略

**P1 - 强制注入（Required）**: {required_str}
- 这些关键词必须出现在简历中
- 可以添加到"专业技能"板块
- 可以在"工作经历"中自然融入（如："使用 **Pandas** 进行数据处理"）

**P2 - 关联注入（Nice-to-have）**: {nice_str}
- 如果用户有类似工具经验，使用关联提及
- 例如：用户有 LlamaIndex 经验 → 添加 "LlamaIndex（熟悉 LangChain 生态）"
- 例如：用户有 MySQL 经验 → 添加 "MySQL（熟悉 PostgreSQL 概念）"

**P3 - 隐含推断**:
- 如果用户做过 LoRA/SFT → 可以推断并添加 PyTorch
- 如果用户做过 RAG 项目 → 可以推断并添加"向量数据库"
- 这些是合理推断，不是造假

**P4 - 弱化处理**: {negative_str}
- 不要删除历史事实
- 将这些技能移到技能列表末尾
- 减少相关描述的篇幅

### 禁止造假规则
- **绝对禁止**发明不存在的公司、项目或工作经历
- 如果某个关键词完全无法自然融入，将其放入"未能融入的建议"列表
"""
        else:
            mode_note = headers['parse_warning'] if parse_failed else headers['general_mode_note']
            mode_section = f"""
## 优化模式：通用润色

> {mode_note}

目标岗位：{target_position if target_position else '未指定'}

专注于：
1. 使用 STAR 法则改善句子表达
2. 统一日期格式和分隔符
3. 提升整体专业性和可读性
"""

        output_template = f"""
## 输出格式

请严格按照以下 Markdown 结构输出：

# {headers['report_title']}

> **注意**: {headers['disclaimer']}

## {headers['strategy_title']}

- **{headers['added_label']}**: [关键词列表] (如果为空，写 "{headers['all_matched_text']}")
- **{headers['associative_label']}**:
  - [关键词] (检测到您有 XXX 经验，已关联提及)
- **{headers['de_emphasized_label']}**: [关键词列表] 或 "无"
- **{headers['unused_label']}**: [关键词列表] 或 "无"

---

## {headers['sections_title']}

### [板块名称]

**{headers['before_label']}**:
[该板块的完整原文]

**{headers['after_label']}**:
[该板块的完整优化文本]

**{headers['changes_label']}**:
- [变更点1]
- [变更点2]
- 统一了日期格式

---

（对每个修改的板块重复上述格式）

### [未修改的板块名称]
{headers['no_changes_text']}
"""

        return base_prompt + strategic_section + mode_section + output_template

    def _build_english_prompt(
        self, headers: dict, target_position: str,
        required_str: str, nice_str: str, negative_str: str,
        is_targeted_mode: bool, parse_failed: bool,
        strategic_section: str = ""
    ) -> str:
        """Build English system prompt."""
        base_prompt = f"""You are a professional ATS (Applicant Tracking System) optimization expert.

## Critical Rules
- **DO NOT use any Emoji symbols**. Output must be plain text Markdown only.
- Keep resume content in its original language, do not translate.
- Only output sections that have been modified. For unchanged sections, write "{headers['no_changes_text']}".
- Both "Before" and "After" must contain the **FULL TEXT** of that section for easy copy-paste replacement.

## Format Standardization (Silent Fixes)
1. **Date Format**: Standardize to `YYYY.MM–YYYY.MM` (using Em dash, no spaces). Remove text like "Enrollment".
2. **Separators**: Convert HTML `<hr>` or `<hr class="...">` to Markdown `---`.
3. Briefly mention these format standardizations in the "Changes" section.

## Polish Method
Use **Implicit STAR Method** to improve weak sentences:
- Do NOT use explicit labels like [Situation], [Task]
- Use natural, professional language following the logic of "Context → Task → Action → Result"
"""

        if is_targeted_mode:
            mode_section = f"""
## Mode: Targeted Optimization

Target Position: {target_position}

### Keyword Injection Strategy

**P1 - Force Inject (Required)**: {required_str}
- These keywords MUST appear in the resume
- Can be added to the "Skills" section
- Can be naturally integrated into "Work Experience" (e.g., "data processing using **Pandas**")

**P2 - Associative Injection (Nice-to-have)**: {nice_str}
- If user has experience with similar tools, use associative mention
- Example: User has LlamaIndex → Add "LlamaIndex (familiar with LangChain ecosystem)"
- Example: User has MySQL → Add "MySQL (familiar with PostgreSQL concepts)"

**P3 - Implied Skills**:
- If user has LoRA/SFT experience → Can infer and add PyTorch
- If user has RAG project → Can infer and add "vector database"
- These are reasonable inferences, not fabrication

**P4 - De-emphasize**: {negative_str}
- Do NOT delete historical facts
- Move these skills to the end of skill lists
- Reduce the word count of related descriptions

### Anti-Fabrication Rules
- **ABSOLUTELY FORBIDDEN** to invent non-existent companies, projects, or work experience
- If a keyword cannot be naturally integrated, add it to the "Unused Suggestions" list
"""
        else:
            mode_note = headers['parse_warning'] if parse_failed else headers['general_mode_note']
            mode_section = f"""
## Mode: General Polish

> {mode_note}

Target Position: {target_position if target_position else 'Not specified'}

Focus on:
1. Using STAR method to improve sentence expression
2. Standardizing date format and separators
3. Improving overall professionalism and readability
"""

        output_template = f"""
## Output Format

Please strictly follow this Markdown structure:

# {headers['report_title']}

> **Note**: {headers['disclaimer']}

## {headers['strategy_title']}

- **{headers['added_label']}**: [Keyword list] (If empty, write "{headers['all_matched_text']}")
- **{headers['associative_label']}**:
  - [Keyword] (Detected you have XXX experience, added as context)
- **{headers['de_emphasized_label']}**: [Keyword list] or "None"
- **{headers['unused_label']}**: [Keyword list] or "None"

---

## {headers['sections_title']}

### [Section Name]

**{headers['before_label']}**:
[Full original text of this section]

**{headers['after_label']}**:
[Full optimized text of this section]

**{headers['changes_label']}**:
- [Change 1]
- [Change 2]
- Unified date format

---

(Repeat the above format for each modified section)

### [Unchanged Section Name]
{headers['no_changes_text']}
"""

        return base_prompt + strategic_section + mode_section + output_template

    # ========== Main Invoke Method ==========
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage, None, None]:
        """
        Main entry point for the resume optimizer tool.
        Refactored to support STREAMING to resolve Dify Cloud timeout issues (TTFB).

        Args:
            tool_parameters: Tool parameters including resume_content, target_position, match_report, language, strategy_context

        Returns:
            Generator of ToolInvokeMessage
        """
        language = tool_parameters.get('language', 'zh_Hans')

        try:
            # 1. Extract parameters
            resume_content = tool_parameters.get('resume_content', '').strip()
            target_position = tool_parameters.get('target_position', '').strip()
            match_report = tool_parameters.get('match_report', '')
            strategy_context = tool_parameters.get('strategy_context', '')  # v0.6.0: Scout integration

            # 2. Validation
            if not resume_content:
                error_msg = "请输入简历内容" if language == 'zh_Hans' else "Please input resume content"
                yield self.create_text_message(error_msg)
                return

            # 3. Parse match_report (Preserve existing logic)
            missing_required, missing_nice, negative_keywords, parse_success = self._parse_match_report(match_report)

            # 4. Determine mode
            is_targeted_mode = bool(match_report and parse_success and (missing_required or missing_nice or negative_keywords))
            parse_failed = bool(match_report and not parse_success)

            # Debug log
            has_strategy = bool(strategy_context)
            print(f"[resume_optimizer] Mode: {'Targeted' if is_targeted_mode else 'General'}, Strategy: {has_strategy}")

            # 5. Build system prompt (with strategic context v0.6.0)
            system_prompt = self._build_system_prompt(
                language=language,
                target_position=target_position,
                missing_required=missing_required,
                missing_nice=missing_nice,
                negative_keywords=negative_keywords,
                is_targeted_mode=is_targeted_mode,
                parse_failed=parse_failed,
                strategy_context=strategy_context
            )

            # 6. Prepare Messages
            prompt_messages = [
                SystemPromptMessage(content=system_prompt),
                UserPromptMessage(content=f"请优化以下简历：\n\n{resume_content}" if language == 'zh_Hans' else f"Please optimize the following resume:\n\n{resume_content}")
            ]

            # 7. LLM Configuration
            llm_config = {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "mode": "chat",
                "completion_params": {
                    "temperature": 0.5,
                    "max_tokens": 8192
                }
            }

            # 8. Streaming Invocation (Critical Fix for TTFB timeout)
            response_generator = self.session.model.llm.invoke(
                model_config=LLMModelConfig(**llm_config),
                prompt_messages=prompt_messages,
                stream=True
            )

            # 9. Yield Chunks immediately to keep connection alive
            # LLMResultChunk structure: chunk.delta.message.content
            has_content = False
            for chunk in response_generator:
                if hasattr(chunk, 'delta') and chunk.delta and hasattr(chunk.delta, 'message') and chunk.delta.message:
                    content = chunk.delta.message.content
                    if content:
                        has_content = True
                        yield self.create_text_message(content)

            # If no content was yielded, show warning
            if not has_content:
                error_msg = "LLM 返回了空内容，请重试" if language == 'zh_Hans' else "LLM returned empty content, please retry"
                yield self.create_text_message(f"\n\n[警告]: {error_msg}" if language == 'zh_Hans' else f"\n\n[Warning]: {error_msg}")

        except Exception as e:
            error_details = str(e)
            print(f"[resume_optimizer] Error: {traceback.format_exc()}")

            # Localized Error Handling
            err_prefix = "[系统错误]" if language == 'zh_Hans' else "[System Error]"

            # Friendly Provider Error
            if "Provider" in error_details and "does not exist" in error_details:
                friendly_msg = "请在 Dify 设置中配置 DeepSeek 提供商" if language == 'zh_Hans' else "Please configure DeepSeek provider in Dify settings"
                yield self.create_text_message(f"\n\n{err_prefix}: {friendly_msg}\n(Details: {error_details})")
            else:
                # General Error
                yield self.create_text_message(f"\n\n{err_prefix}: {error_details}")

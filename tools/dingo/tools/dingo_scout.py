"""
Dingo Scout - Strategic Job Hunting Module

v1.0.0 - Initial Release

Features:
1. Natural language user profile parsing
2. Industry report analysis (company extraction, financial signals)
3. Person-job fit scoring algorithm with sub-scores
4. Search strategy generation
5. Interview style prediction
6. Grounding: All conclusions require source quotes

Algorithm:
- Score = weighted sum of (skill_match, risk_alignment, career_stage_fit, location_match, financial_health)
- Tier 1: match_score >= 0.75
- Tier 2: match_score >= 0.50
- Not Recommended: match_score < 0.50 or financial_status = "contraction"
"""

import json
import os
import time
from typing import Any
from collections.abc import Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.llm import LLMModelConfig
from dify_plugin.entities.model.message import SystemPromptMessage, UserPromptMessage


# ============================================================================
# SYSTEM PROMPT - Core LLM Analysis Logic
# ============================================================================

SCOUT_SYSTEM_PROMPT = """你是 Dingo Scout，一位专业的求职战略分析师。
你的任务是从复杂的行业报告中提取对求职者有价值的信息，并生成精准的求职战略。

## 重要规则

1. **禁止使用任何 Emoji 符号**。输出必须是纯文本。
2. **只分析报告中明确提及的公司**，不要推测未提及的公司。
3. **所有财务判断必须附带原文引用 (Grounding)**。
4. 如果报告中只有"片汤话"而无具体数据，输出 confidence < 0.5。

---

## 1. 用户画像解析 (User Profile Parsing)

**输入格式**:
- user_profile: 自然语言或 JSON（必需）
- resume_text: 完整简历文本（可选）

**解析策略**:

**情况 A - 同时提供 resume_text 和 user_profile**:
1. 从 resume_text 提取详细技能列表（硬技能：编程语言、框架、工具）
2. 从 resume_text 提取项目经验和工作年限
3. 从 user_profile 提取偏好信息（地点、风险偏好、薪资预期等软偏好）
4. 合并后用于 scoring_breakdown.skill_match 计算，提升匹配精度
5. 不需要输出额外字段，仅让评分更准确

**情况 B - 仅提供 user_profile**:
按以下规则从自然语言中提取所有信息。

**自然语言示例**:
"我是23届的CS硕士，在字节做过大模型应用实习，会Python和PyTorch，想找个大厂，最好在北京。"

**解析规则**:

| 维度 | 提取方法 | 默认值 |
|------|----------|--------|
| 学历 | "硕士/Master" -> Master, "本科/Bachelor" -> Bachelor | Bachelor |
| 专业 | "CS/计算机/软件" -> CS, "EE/电子" -> EE | CS |
| 经验年限 | "实习" -> 0-1年, "3年经验" -> 3年 | 0 |
| 技术栈 | 提取所有技术关键词 | [] |
| 风险偏好 | "大厂/稳定" -> conservative, "创业公司" -> aggressive | moderate |
| 职业阶段 | "应届/23届" -> new_grad, "3年" -> junior | new_grad |
| 地点偏好 | 提取城市名 | [] |

**模糊推断**:
- "想找大厂" -> risk_preference = conservative
- "不介意加班" -> 可接受高强度文化
- "有女朋友在上海" -> location_preference = ["上海"]

---

## 2. 报告信息提取与 Grounding

### 2.1 公司列表提取
提取所有被提及的公司名称（包括简称、全称、英文名）。

### 2.2 财务信号分类

**Expansion (扩张)**: ROE 上升、主力资金净流入、新业务线、扩招信号
**Stable (稳健)**: ROE 平稳、资金流平衡、业务维护期
**Contraction (收缩)**: ROE 下降、资金流出、裁员传闻、业务收缩
**Uncertain**: 存在矛盾信号（如营收增但利润降）
**Unknown**: 报告中无该公司的具体财务数据

### 2.3 Grounding 规则 (关键!)

**所有财务判断必须附带原文引用**:

```json
"financial_evidence": {
  "source_quotes": [
    "豆包商业化加速，AI 落地团队扩编 30%（报告第3段）",
    "ROE 同比上升 15%（报告第1段）"
  ],
  "confidence": 0.9,
  "conflicting_signals": null
}
```

**如果存在矛盾信号**:
```json
"financial_evidence": {
  "source_quotes": [
    "营收同比增长 20%（报告第2段）",
    "但净利润下滑 15%（报告第4段）"
  ],
  "confidence": 0.5,
  "conflicting_signals": "营收增长但利润下滑，扩张可持续性存疑"
}
```

**有效证据 vs 无效证据**:

| 有效证据 | 无效证据 |
|----------|----------|
| "ROE 上升 15%" | "我们致力于创新" |
| "资金净流入 50 亿" | "未来可期" |
| "团队扩编 30%" | "行业领先地位" |
| "裁员 2000 人" | "优化组织架构" |

**禁止行为**:
1. 禁止将 A 公司的数据用于 B 公司的判断
2. 禁止从"片汤话"中推断财务状态
3. 如果只有无效证据，必须输出 confidence < 0.5

---

## 3. 人岗匹配逻辑

### Tier 1 (核心目标) - 同时满足:
1. 技能匹配度 >= 70%
2. 风险偏好匹配 (conservative -> 大厂, aggressive -> 可接受创业)
3. 财务状态为 expansion 或 stable
4. 证据置信度 >= 0.7

### Tier 2 (潜在机会) - 满足任一:
1. 技能匹配度 50-70%，但公司 expansion
2. 技能匹配度 >= 70%，但公司 stable（成长空间有限）
3. 存在矛盾信号 (conflicting_signals)

### Insufficient Data (数据不足) - 满足全部:
1. 报告中未提供该公司的具体财务数据（financial_status = unknown）
2. 但该公司属于行业公认龙头或大厂（如 BAT、字节、美团、华为等）
3. 技能匹配度 >= 50%

**处理方式**: 放入 `insufficient_data` 列表，建议用户自行搜索该公司最新财报。
**不要放入 Not Recommended！**

### Not Recommended - 满足任一:
1. 公司 contraction（有明确收缩证据）
2. 技能匹配度 < 50%
3. 证据置信度 < 0.5 且公司非行业龙头

---

## 4. 评分维度 (scoring_breakdown)

请为每个公司输出以下子分数，系统将加权计算总分：

```json
"scoring_breakdown": {
  "skill_match": {
    "score": 0.0-1.0,
    "matched_skills": ["Python", "PyTorch"],
    "missing_skills": ["Go"],
    "reasoning": "用户 LLM 经验与 AI 落地需求匹配"
  },
  "risk_alignment": {
    "score": 0.0-1.0,
    "user_preference": "conservative",
    "company_risk_level": "low",
    "reasoning": "大厂 + 扩张期，符合稳定偏好"
  },
  "career_stage_fit": {
    "score": 0.0-1.0,
    "user_stage": "new_grad",
    "company_fit": "有完善培养体系",
    "reasoning": "字节有成熟的新人培养机制"
  },
  "location_match": {
    "score": 0.0-1.0,
    "user_preference": ["北京", "上海"],
    "company_locations": ["北京"],
    "reasoning": "完全匹配"
  },
  "financial_health": {
    "score": 0.0-1.0,
    "status": "expansion",
    "reasoning": "ROE上升，资金充裕"
  }
}
```

---

## 5. 输出格式

请严格按照以下 JSON 结构输出：

```json
{
  "strategy_context": {
    "target_companies": [
      {
        "name": "公司名称",
        "financial_status": "expansion|stable|contraction|uncertain|unknown",
        "financial_evidence": {
          "source_quotes": ["原文引用1", "原文引用2"],
          "confidence": 0.0-1.0,
          "conflicting_signals": "矛盾说明或null"
        },
        "scoring_breakdown": { ... },
        "match_reasoning": "为什么匹配（50字以内）",
        "hiring_trigger": "具体的扩招原因",
        "search_keywords": ["关键词1", "关键词2"],
        "recommended_platforms": ["Boss直聘", "拉勾"],
        "interview_style": "面试风格描述",
        "interview_prep_tips": [
          "算法: 具体建议",
          "系统设计: 具体建议",
          "项目: 具体建议"
        ],
        "salary_leverage": "薪资谈判筹码分析",
        "culture_fit": "文化匹配度分析",
        "timing_advice": "最佳投递时机"
      }
    ],
    "insufficient_data": [
      {
        "name": "公司名称（行业龙头但报告无具体数据）",
        "reason": "报告中缺乏该公司的具体财务数据",
        "available_info": ["行业地位描述等非量化信息"],
        "suggestion": "建议自行搜索该公司最新财报"
      }
    ],
    "not_recommended": [
      {
        "name": "公司名称",
        "reason": "不推荐原因（需有明确收缩证据或技能严重不匹配）"
      }
    ],
    "meta": {
      "report_date": "从报告中提取或填今天日期",
      "analysis_confidence": 0.0-1.0,
      "user_profile_summary": "用户画像摘要（如：23届CS硕士，LLM经验，conservative）"
    }
  }
}
```

---

现在，请分析用户提供的行业报告和用户画像，生成战略上下文卡片。
"""


class SchemaValidationError(Exception):
    """Custom exception for schema validation failures."""
    pass


class DingoScout(Tool):
    """
    Strategic job hunting module that analyzes industry reports
    and user profiles to generate targeted recommendations.
    """

    # Scoring weights (configurable)
    SCORE_WEIGHTS = {
        "skill_match": 0.40,
        "risk_alignment": 0.20,
        "career_stage_fit": 0.15,
        "location_match": 0.10,
        "financial_health": 0.15
    }

    # Tier thresholds
    TIER_THRESHOLDS = {
        "tier1": 0.75,
        "tier2": 0.50
    }

    # Confidence thresholds
    CONFIDENCE_THRESHOLDS = {
        "tier1_min": 0.7,
        "tier2_min": 0.5,
        "insufficient": 0.5
    }

    MAX_RETRIES = 2

    # Company URL data cache
    _company_urls: dict = None

    # ========================================================================
    # Company URL Loading
    # ========================================================================

    def _load_company_urls(self) -> dict:
        """
        Load company recruitment URLs from JSON data file.
        Returns empty dict if file not found or parse error.
        """
        if DingoScout._company_urls is not None:
            return DingoScout._company_urls

        try:
            # Get path relative to this script: ../data/company_urls.json
            current_dir = os.path.dirname(os.path.abspath(__file__))
            data_path = os.path.join(current_dir, '..', 'data', 'company_urls.json')
            data_path = os.path.normpath(data_path)

            with open(data_path, 'r', encoding='utf-8') as f:
                DingoScout._company_urls = json.load(f)
                print(f"[Scout] Loaded {len(DingoScout._company_urls)} company URLs")
                return DingoScout._company_urls

        except FileNotFoundError:
            print(f"[Scout] company_urls.json not found, skipping URL injection")
            DingoScout._company_urls = {}
            return {}
        except json.JSONDecodeError as e:
            print(f"[Scout] Failed to parse company_urls.json: {e}")
            DingoScout._company_urls = {}
            return {}
        except Exception as e:
            print(f"[Scout] Error loading company URLs: {e}")
            DingoScout._company_urls = {}
            return {}

    def _inject_urls(self, companies: list) -> None:
        """
        Inject recruitment URLs into company data.
        Uses exact match on company name (full name or short name).
        """
        url_map = self._load_company_urls()
        if not url_map:
            return

        for company in companies:
            name = company.get("name", "")
            if not name:
                continue

            # Exact match lookup
            url = url_map.get(name)
            if url:
                company["recruitment_url"] = url

    # ========================================================================
    # Main Entry Point
    # ========================================================================

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Main entry point for Dingo Scout.

        Args:
            tool_parameters:
                - industry_report (str): Raw industry/financial report text
                - user_profile (str): Natural language or JSON user profile
                - resume_text (str, optional): Full resume text for skill extraction
                - output_format (str): 'markdown' | 'json'

        Returns:
            - JSON message: strategy_context
            - Text message: Human-readable strategy card (if markdown)
        """
        try:
            industry_report = tool_parameters.get('industry_report', '').strip()
            user_profile = tool_parameters.get('user_profile', '').strip()
            resume_text = tool_parameters.get('resume_text', '').strip()
            output_format = tool_parameters.get('output_format', 'markdown')

            # Validation
            if not industry_report:
                yield self.create_text_message("[Error] 请提供行业报告")
                return

            if not user_profile:
                yield self.create_text_message("[Error] 请提供用户画像")
                return

            # Build user prompt with optional resume
            if resume_text:
                user_content = f"""### 行业报告:
{industry_report}

### 用户画像:
{user_profile}

### 个人简历 (用于技能提取，提升匹配精度):
{resume_text}

请分析并输出战略上下文卡片 (JSON 格式)。
注意：已提供简历，请从中提取技能列表用于 skill_match 评分计算。"""
            else:
                user_content = f"""### 行业报告:
{industry_report}

### 用户画像:
{user_profile}

请分析并输出战略上下文卡片 (JSON 格式)。"""

            # Invoke LLM with retry
            try:
                raw_result = self._invoke_llm_with_retry(
                    system_prompt=SCOUT_SYSTEM_PROMPT,
                    user_content=user_content
                )
            except Exception as e:
                yield self.create_text_message(
                    f"[Warning] LLM 分析失败: {str(e)}\n\n"
                    "建议:\n"
                    "1. 检查行业报告是否包含具体公司和财务数据\n"
                    "2. 尝试简化报告内容后重试\n"
                    "3. 手动提取关键公司信息"
                )
                return

            # Apply safe defaults
            result = self._safe_parse_with_defaults(raw_result)

            # Calculate scores and filter by confidence
            result = self._process_llm_result(result)

            # Output
            yield self.create_json_message(result)

            if output_format == 'json':
                json_str = json.dumps(result, ensure_ascii=False, indent=2)
                yield self.create_text_message(json_str)
            else:
                summary = self._create_markdown_summary(result)
                yield self.create_text_message(summary)

        except Exception as e:
            import traceback
            print(f"[Scout] Unexpected error: {traceback.format_exc()}")
            yield self.create_text_message(f"[Error] 战略分析失败: {str(e)}")

    # ========================================================================
    # LLM Invocation with Retry
    # ========================================================================

    def _get_llm_config(self) -> dict:
        """Get LLM configuration."""
        return {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "mode": "chat",
            "completion_params": {
                "temperature": 0.3,
                "max_tokens": 6000
            }
        }

    def _invoke_llm_with_retry(
        self,
        system_prompt: str,
        user_content: str
    ) -> dict:
        """
        Invoke LLM with retry mechanism for JSON parsing.
        On failure, sends error message back to LLM for correction.
        """
        last_error = None
        last_response = None

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                # Build prompt
                if attempt == 0:
                    current_prompt = user_content
                else:
                    current_prompt = self._build_retry_prompt(
                        original_request=user_content,
                        last_response=last_response,
                        error_message=str(last_error)
                    )

                # Call LLM with streaming to avoid TTFB timeout
                response_generator = self.session.model.llm.invoke(
                    model_config=LLMModelConfig(**self._get_llm_config()),
                    prompt_messages=[
                        SystemPromptMessage(content=system_prompt),
                        UserPromptMessage(content=current_prompt)
                    ],
                    stream=True
                )

                # Collect all chunks into complete response
                collected_content = []
                for chunk in response_generator:
                    try:
                        if content := chunk.delta.message.content:
                            collected_content.append(content)
                    except AttributeError:
                        # Skip chunks that don't have the expected .delta.message.content structure
                        continue

                last_response = "".join(collected_content).strip()

                # Try to parse JSON
                result = self._parse_json_response(last_response)

                # Validate schema
                self._validate_schema(result)

                return result

            except json.JSONDecodeError as e:
                last_error = f"JSON 解析失败: {str(e)}"
                print(f"[Scout] Attempt {attempt + 1} failed: {last_error}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(1)

            except SchemaValidationError as e:
                last_error = f"Schema 校验失败: {str(e)}"
                print(f"[Scout] Attempt {attempt + 1} failed: {last_error}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(1)

            except Exception as e:
                last_error = str(e)
                print(f"[Scout] Attempt {attempt + 1} failed: {last_error}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(1)

        raise Exception(f"LLM 输出解析失败，已重试 {self.MAX_RETRIES} 次: {last_error}")

    def _build_retry_prompt(
        self,
        original_request: str,
        last_response: str,
        error_message: str
    ) -> str:
        """Build retry prompt with error feedback."""
        return f"""你上一次的输出有格式问题，请修正。

## 错误信息
{error_message}

## 你上次的输出 (有问题)
```
{last_response[:2000]}...
```

## 原始请求
{original_request}

## 修正要求
1. 确保输出是有效的 JSON 格式
2. 确保所有字符串使用双引号
3. 确保 target_companies 是一个数组
4. 确保每个公司都有 name, financial_status, financial_evidence 字段

请重新输出正确的 JSON。
"""

    # ========================================================================
    # JSON Parsing and Validation
    # ========================================================================

    def _parse_json_response(self, response_text: str) -> dict:
        """Extract and parse JSON from LLM response."""
        text = response_text.strip()

        # Remove markdown code blocks
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]

        # Find JSON boundaries
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            text = text[start:end+1]

        return json.loads(text.strip())

    def _validate_schema(self, data: dict) -> None:
        """
        Validate LLM output against expected schema.
        Raises SchemaValidationError if validation fails.
        """
        errors = []

        if "strategy_context" not in data:
            errors.append("缺少 strategy_context 字段")
        else:
            context = data["strategy_context"]

            # Check target_companies
            if "target_companies" not in context:
                errors.append("缺少 target_companies 字段")
            elif not isinstance(context["target_companies"], list):
                errors.append("target_companies 必须是数组")
            else:
                for i, company in enumerate(context["target_companies"]):
                    company_errors = self._validate_company(company, i)
                    errors.extend(company_errors)

            # Check meta
            if "meta" not in context:
                errors.append("缺少 meta 字段")

        if errors:
            raise SchemaValidationError("\n".join(errors))

    def _validate_company(self, company: dict, index: int) -> list[str]:
        """Validate a single company object."""
        errors = []
        prefix = f"target_companies[{index}]"

        if "name" not in company:
            errors.append(f"{prefix}: 缺少 name 字段")

        if "financial_status" not in company:
            errors.append(f"{prefix}: 缺少 financial_status 字段")
        elif company["financial_status"] not in ["expansion", "stable", "contraction", "uncertain", "unknown"]:
            errors.append(f"{prefix}: financial_status 值无效: {company['financial_status']}")

        return errors


    # ========================================================================
    # Score Calculation and Result Processing
    # ========================================================================

    def _safe_parse_with_defaults(self, data: dict) -> dict:
        """Apply safe defaults for missing optional fields."""
        context = data.get("strategy_context", {})

        for company in context.get("target_companies", []):
            company.setdefault("tier", None)
            company.setdefault("match_score", None)
            company.setdefault("search_keywords", [])
            company.setdefault("recommended_platforms", ["Boss直聘"])
            company.setdefault("interview_style", "待确认")
            company.setdefault("interview_prep_tips", [])
            company.setdefault("salary_leverage", "待分析")
            company.setdefault("culture_fit", "待分析")
            company.setdefault("financial_evidence", {
                "source_quotes": [],
                "confidence": 0.5,
                "conflicting_signals": None
            })
            company.setdefault("scoring_breakdown", {})

        context.setdefault("not_recommended", [])
        meta = context.setdefault("meta", {})
        meta.setdefault("analysis_confidence", 0.5)
        meta.setdefault("report_date", "未知")
        meta.setdefault("user_profile_summary", "")

        return data

    def _calculate_match_score(self, scoring_breakdown: dict) -> tuple[float, str]:
        """
        Calculate weighted match score from LLM sub-scores.
        Returns: (match_score, tier)
        """
        total_score = 0.0
        total_weight = 0.0

        for dimension, weight in self.SCORE_WEIGHTS.items():
            if dimension in scoring_breakdown:
                sub_score = scoring_breakdown[dimension].get("score", 0.0)
                if sub_score is not None:
                    total_score += sub_score * weight
                    total_weight += weight

        if total_weight > 0:
            match_score = round(total_score / total_weight, 2)
        else:
            match_score = 0.5  # Default when no scoring data

        # Determine tier
        if match_score >= self.TIER_THRESHOLDS["tier1"]:
            tier = "Tier 1"
        elif match_score >= self.TIER_THRESHOLDS["tier2"]:
            tier = "Tier 2"
        else:
            tier = "Not Recommended"

        return match_score, tier

    def _filter_by_confidence(self, companies: list) -> tuple[list, list, list]:
        """
        Filter companies by financial evidence confidence.
        Returns: (qualified, insufficient_data, not_recommended)
        """
        qualified = []
        insufficient = []
        not_recommended = []

        for company in companies:
            evidence = company.get("financial_evidence", {})
            confidence = evidence.get("confidence", 0.0)
            status = company.get("financial_status", "unknown")

            # Contraction: directly exclude
            if status == "contraction":
                quotes = evidence.get("source_quotes", ["无"])
                quote_preview = quotes[0][:50] if quotes else "无"
                not_recommended.append({
                    "name": company["name"],
                    "reason": f"财务收缩期 (证据: {quote_preview}...)"
                })
                continue

            # Low confidence: insufficient data
            if confidence < self.CONFIDENCE_THRESHOLDS["insufficient"]:
                insufficient.append({
                    "name": company["name"],
                    "reason": "报告中缺乏该公司的具体财务数据",
                    "available_info": evidence.get("source_quotes", []),
                    "suggestion": "建议自行搜索该公司最新财报或招聘动态"
                })
                continue

            # Conflicting signals: downgrade to Tier 2
            if evidence.get("conflicting_signals"):
                company["tier"] = "Tier 2"
                company["risk_warning"] = evidence["conflicting_signals"]

            qualified.append(company)

        return qualified, insufficient, not_recommended

    def _process_llm_result(self, llm_data: dict) -> dict:
        """Post-process LLM output with score calculation and confidence filtering."""
        context = llm_data.get("strategy_context", {})
        companies = context.get("target_companies", [])

        # 1. Calculate scores for each company
        for company in companies:
            scoring = company.get("scoring_breakdown", {})
            if scoring:
                match_score, tier = self._calculate_match_score(scoring)
                company["match_score"] = match_score
                company["tier"] = tier
            else:
                # Use LLM-provided score if no breakdown
                if company.get("match_score") is None:
                    company["match_score"] = 0.5
                if company.get("tier") is None:
                    company["tier"] = "Tier 2"

        # 2. Inject recruitment URLs
        self._inject_urls(companies)

        # 3. Filter by confidence
        qualified, insufficient, llm_not_recommended = self._filter_by_confidence(companies)

        # 4. Merge with LLM's not_recommended
        all_not_recommended = llm_not_recommended + context.get("not_recommended", [])

        # 5. Sort by score
        qualified.sort(key=lambda x: x.get("match_score", 0), reverse=True)

        return {
            "strategy_context": {
                "target_companies": qualified,
                "insufficient_data": insufficient,
                "not_recommended": all_not_recommended,
                "meta": context.get("meta", {})
            }
        }


    # ========================================================================
    # Markdown Output Generation
    # ========================================================================

    def _create_markdown_summary(self, result: dict) -> str:
        """Create human-readable markdown summary."""
        lines = [
            "# Dingo Scout 战略分析报告",
            "",
            "> 基于您提供的行业报告和个人画像，为您生成以下求职战略建议。",
            "",
            "---",
            "",
        ]

        context = result.get("strategy_context", {})
        target_companies = context.get("target_companies", [])
        insufficient_data = context.get("insufficient_data", [])
        not_recommended = context.get("not_recommended", [])
        meta = context.get("meta", {})

        # Tier 1 & Tier 2 companies
        tier1 = [c for c in target_companies if c.get("tier") == "Tier 1"]
        tier2 = [c for c in target_companies if c.get("tier") == "Tier 2"]

        if tier1:
            lines.append("## [Tier 1] 核心目标公司")
            lines.append("")
            for i, company in enumerate(tier1, 1):
                lines.extend(self._format_company(i, company))

        if tier2:
            lines.append("## [Tier 2] 潜在机会")
            lines.append("")
            for i, company in enumerate(tier2, 1):
                lines.extend(self._format_company(i, company))

        if insufficient_data:
            lines.append("## [Insufficient Data] 数据不足")
            lines.append("")
            lines.append("以下公司在报告中缺乏具体财务数据，建议自行搜索：")
            lines.append("")
            lines.append("| 公司 | 原因 | 建议 |")
            lines.append("|------|------|------|")
            for item in insufficient_data:
                lines.append(f"| {item.get('name', '')} | {item.get('reason', '')} | {item.get('suggestion', '')} |")
            lines.append("")

        if not_recommended:
            lines.append("## [Not Recommended] 不推荐公司")
            lines.append("")
            lines.append("| 公司 | 原因 |")
            lines.append("|------|------|")
            for item in not_recommended:
                lines.append(f"| {item.get('name', '')} | {item.get('reason', '')} |")
            lines.append("")

        # Action items
        if tier1:
            top_company = tier1[0]
            keywords = top_company.get("search_keywords", [""])
            platforms = top_company.get("recommended_platforms", ["Boss直聘"])

            lines.extend([
                "---",
                "",
                "## [Action] 下一步行动",
                "",
                f"1. 前往 {', '.join(platforms[:2])} 搜索 \"{top_company.get('name', '')} + {keywords[0] if keywords else ''}\"",
                "2. 找到真实 JD 后，复制 JD 文本",
                "3. 使用 Dingo Keyword Matcher 分析匹配度",
                "4. 使用 Dingo Resume Optimizer 优化简历（记得传入本战略卡片）",
                "",
            ])

        # Footer
        confidence_pct = int(meta.get('analysis_confidence', 0) * 100)
        lines.extend([
            "---",
            "",
            f"报告生成时间: {meta.get('report_date', 'N/A')} | 分析置信度: {confidence_pct}%",
            f"用户画像摘要: {meta.get('user_profile_summary', 'N/A')}",
        ])

        return "\n".join(lines)

    def _format_company(self, index: int, company: dict) -> list[str]:
        """Format a single company section."""
        score_pct = int(company.get('match_score', 0) * 100)
        evidence = company.get('financial_evidence', {})
        confidence_pct = int(evidence.get('confidence', 0) * 100)

        lines = [
            f"### {index}. {company.get('name', 'Unknown')}",
        ]

        # Recruitment URL (if available)
        if company.get('recruitment_url'):
            lines.append(f"🔗 [官方招聘入口]({company.get('recruitment_url')})")

        lines.append(f"**匹配度**: {score_pct}% | **置信度**: {confidence_pct}%")
        lines.append("")

        # Match reasoning
        if company.get('match_reasoning'):
            lines.append(f"**为什么推荐**: {company.get('match_reasoning')}")
            lines.append("")

        # Financial status with evidence
        lines.append(f"**财务状态**: [{company.get('financial_status', 'unknown')}]")
        if company.get('hiring_trigger'):
            lines.append(f"- {company.get('hiring_trigger')}")

        # Evidence chain
        source_quotes = evidence.get('source_quotes', [])
        if source_quotes:
            lines.append("")
            lines.append("**证据链**:")
            for quote in source_quotes[:3]:
                lines.append(f"> {quote}")

        # Risk warning
        if company.get('risk_warning'):
            lines.append("")
            lines.append(f"**风险提示**: {company.get('risk_warning')}")

        lines.append("")

        # Search strategy
        lines.append("**搜索策略**:")
        keywords = company.get('search_keywords', [])
        platforms = company.get('recommended_platforms', [])
        lines.append(f"- 关键词: {', '.join(keywords) if keywords else '待确认'}")
        lines.append(f"- 推荐平台: {', '.join(platforms) if platforms else 'Boss直聘'}")
        if company.get('timing_advice'):
            lines.append(f"- 最佳时机: {company.get('timing_advice')}")
        lines.append("")

        # Interview prep
        prep_tips = company.get('interview_prep_tips', [])
        if prep_tips:
            lines.append("**面试准备**:")
            for tip in prep_tips:
                lines.append(f"- {tip}")
            lines.append("")

        # Salary and culture
        lines.append(f"**薪资谈判**: {company.get('salary_leverage', '待分析')}")
        lines.append("")
        lines.append(f"**文化匹配**: {company.get('culture_fit', '待分析')}")
        lines.append("")
        lines.append("---")
        lines.append("")

        return lines

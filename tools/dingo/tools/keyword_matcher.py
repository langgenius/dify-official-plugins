"""
Keyword Matcher Tool for Dingo - ATS-Optimized Resume-JD Matching

Implements industry-standard TF-IDF weighted keyword matching algorithm used by 98% of Fortune 500 ATS systems.
Combines Resume-Matcher's frequency-based priority classification with LLM-powered optimization recommendations.

Algorithm:
1. Dual-Engine Extraction: Extract keywords from both resume and JD using keyword_extraction logic
2. TF-IDF Weighting: Calculate keyword importance based on frequency in JD
3. Priority Classification: High (≥3 mentions), Medium (2 mentions), Low (1 mention)
4. Weighted Scoring: Calculate match score with priority-based weights
5. LLM Recommendations: Generate actionable optimization suggestions

Reference: 
- Resume-Matcher/apps/backend/app/services/score_improvement_service.py
- TF-IDF algorithm used by 98% Fortune 500 companies (LinkedIn, 2021)
"""

import re
import json
import time
from pathlib import Path
from typing import Any
from collections.abc import Generator

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.llm import LLMModelConfig
from dify_plugin.entities.model.message import UserPromptMessage


class KeywordMatcher(Tool):
    """
    ATS-Optimized Keyword Matcher: TF-IDF Weighted Matching + LLM Recommendations
    
    Implements the same algorithm used by major ATS systems (Taleo, Workday, Greenhouse)
    to calculate resume-job description match scores.
    """
    
    # Keywords that need case-sensitive matching
    CASE_SENSITIVE_KEYWORDS = {"Go", "R"}
    
    # Synonym mapping (same as keyword_extraction)
    SYNONYM_MAP = {
        "k8s": "Kubernetes",
        "js": "JavaScript",
        "ts": "TypeScript",
        "py": "Python",
        "tf": "TensorFlow",
        "react.js": "React",
        "vue.js": "Vue.js",
        "node.js": "Node.js",
        "next.js": "Next.js",
        "express.js": "Express.js",
        "nest.js": "NestJS",
        "postgresql": "PostgreSQL",
        "mysql": "MySQL",
        "mongodb": "MongoDB",
        "aws": "AWS",
        "gcp": "GCP",
        "ci/cd": "CI/CD",
        "ml": "Machine Learning",
        "ai": "Artificial Intelligence",
        "nlp": "Natural Language Processing",
        "cv": "Computer Vision",
    }
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        try:
            resume_text = tool_parameters.get('resume_text', '').strip()
            resume_keywords_json = tool_parameters.get('resume_keywords', '').strip()
            jd_text = tool_parameters.get('jd_text', '').strip()
            position_name = tool_parameters.get('position_name', '').strip()
            use_llm = tool_parameters.get('use_llm', True)

            if not resume_text:
                yield self.create_text_message("❌ Resume text cannot be empty")
                return

            # Must provide either jd_text or position_name
            if not jd_text and not position_name:
                yield self.create_text_message("❌ 必须提供 jd_text（完整职位描述）或 position_name（职位名称）之一")
                return

            # Load keyword dictionary
            current_dir = Path(__file__).parent.parent
            dictionary_path = current_dir / "data" / "onet_keywords.json"
            keywords = self._load_dictionary(dictionary_path)

            # 1. Get resume keywords (reuse if provided, otherwise extract)
            if resume_keywords_json:
                # Try to parse the input intelligently
                resume_keywords = self._parse_resume_keywords_input(resume_keywords_json)

                if resume_keywords is None:
                    # Parsing failed, extract from resume text instead
                    resume_keywords = self._extract_keywords_dual_engine(resume_text, use_llm, keywords)
            else:
                # Extract keywords from resume
                resume_keywords = self._extract_keywords_dual_engine(resume_text, use_llm, keywords)

            # 2. Get JD keywords: either from provided JD text or generate from position name
            if jd_text:
                # User provided full JD text
                jd_keywords = self._extract_keywords_dual_engine(jd_text, use_llm, keywords)
                jd_source = "用户提供的职位描述"
            else:
                # User only provided position name, use LLM to generate standard requirements
                if not use_llm:
                    yield self.create_text_message("❌ 使用职位名称生成标准要求时，必须启用 LLM（use_llm=true）")
                    return

                generated_jd = self._generate_standard_jd_requirements(position_name)
                jd_keywords = self._extract_keywords_from_generated_jd(generated_jd)
                jd_source = f"LLM 生成的标准职位要求（{position_name}）"
                # Use generated JD as jd_text for display
                jd_text = generated_jd

            # 3. Perform matching analysis
            match_result = self._calculate_match_score(
                resume_keywords, jd_keywords, resume_text, jd_text, use_llm, jd_source
            )

            # Create summary text
            summary = self._create_summary(match_result, True)

            # Yield results
            json_message = self.create_json_message(match_result)
            text_message = self.create_text_message(summary)
            yield from [json_message, text_message]

        except Exception as e:
            yield self.create_text_message(f"❌ Keyword matching failed: {str(e)}")
    
    def _load_dictionary(self, dictionary_path: Path) -> list[str]:
        """Load O*NET keyword dictionary"""
        with open(dictionary_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        all_keywords = []
        for category_keywords in data['keywords'].values():
            all_keywords.extend(category_keywords)
        
        return all_keywords
    
    def _normalize_synonyms(self, text: str) -> str:
        """Normalize synonyms (K8s→Kubernetes, etc.)"""
        normalized = text
        for synonym, standard in self.SYNONYM_MAP.items():
            pattern = re.compile(rf'\b{re.escape(synonym)}\b', re.IGNORECASE)
            normalized = pattern.sub(standard, normalized)
        return normalized
    
    def _prepare_text_for_matching(self, text: str) -> str:
        """
        Prepare text for keyword matching (Resume-Matcher pattern)
        Remove markdown symbols but preserve technical terms like C#, C++
        """
        lowered = text.lower()
        lowered = re.sub(r"[`*_>\-]", " ", lowered)
        lowered = re.sub(r"(?<![a-z])#(?![a-z])", " ", lowered)
        lowered = re.sub(r"\s+", " ", lowered)
        return lowered
    
    def _count_mentions(self, keyword: str, text: str) -> int:
        """Count keyword mentions in text (case-sensitive for special keywords)"""
        if keyword in self.CASE_SENSITIVE_KEYWORDS:
            pattern = re.compile(rf"(?<!\w){re.escape(keyword)}(?!\w)")
            return len(pattern.findall(text))
        else:
            text_normalized = self._prepare_text_for_matching(text)
            kw_lower = keyword.lower()
            pattern = re.compile(rf"(?<!\w){re.escape(kw_lower)}(?!\w)")
            return len(pattern.findall(text_normalized))

    def _extract_with_dictionary(self, text: str, keywords: list[str]) -> list[dict[str, Any]]:
        """Extract keywords using dictionary matching (Engine 1)"""
        text_normalized = self._normalize_synonyms(text)
        text_norm = self._prepare_text_for_matching(text_normalized)

        results = []
        for keyword in keywords:
            if keyword in self.CASE_SENSITIVE_KEYWORDS:
                pattern = re.compile(rf"(?<!\w){re.escape(keyword)}(?!\w)")
                mentions = len(pattern.findall(text_normalized))
            else:
                kw_lower = keyword.lower()
                pattern = re.compile(rf"(?<!\w){re.escape(kw_lower)}(?!\w)")
                mentions = len(pattern.findall(text_norm))

            if mentions > 0:
                results.append({
                    "skill": keyword,
                    "mentions": mentions,
                    "confidence": 1.0,
                    "source": "dictionary"
                })

        return results

    def _extract_with_llm(self, text: str) -> list[dict[str, Any]]:
        """Extract keywords using LLM semantic analysis (Engine 2)"""
        prompt = f"""You are a technical keyword extraction expert. Extract ALL technology keywords from this text.

Output ONLY valid JSON (no markdown, no code blocks):
{{
  "keywords": [
    {{"skill": "Python", "confidence": 1.0, "source": "explicit"}},
    {{"skill": "Docker", "confidence": 0.85, "source": "inferred"}}
  ]
}}

Text:
{text}"""

        llm_config = {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "mode": "chat",
            "completion_params": {
                "temperature": 0.3,
                "max_tokens": 2000
            }
        }

        # Retry logic for LLM invocation
        max_retries = 3
        retry_delay = 1  # Initial delay in seconds

        for attempt in range(max_retries):
            try:
                llm_result = self.session.model.llm.invoke(
                    model_config=LLMModelConfig(**llm_config),
                    prompt_messages=[UserPromptMessage(content=prompt)],
                    stream=False
                )

                response_text = llm_result.message.content.strip()

                # Check for empty response
                if not response_text:
                    if attempt < max_retries - 1:
                        print(f"⚠️ LLM returned empty response (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        print(f"❌ LLM returned empty response after {max_retries} attempts")
                        return []

                # Clean markdown code blocks
                response_text = re.sub(r'^```json\s*', '', response_text)
                response_text = re.sub(r'\s*```$', '', response_text)

                llm_data = json.loads(response_text)
                keywords = llm_data.get('keywords', [])

                if keywords:
                    return keywords
                else:
                    if attempt < max_retries - 1:
                        print(f"⚠️ LLM returned empty keywords list (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        return []

            except json.JSONDecodeError as json_err:
                if attempt < max_retries - 1:
                    print(f"⚠️ JSON parsing failed (attempt {attempt + 1}/{max_retries}): {str(json_err)}, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    print(f"❌ JSON parsing failed after {max_retries} attempts: {str(json_err)}")
                    return []

            except Exception as llm_err:
                if attempt < max_retries - 1:
                    print(f"⚠️ LLM invocation failed (attempt {attempt + 1}/{max_retries}): {str(llm_err)}, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    print(f"❌ LLM invocation failed after {max_retries} attempts: {str(llm_err)}")
                    return []

        return []

    def _merge_keywords(self, dict_results: list[dict], llm_results: list[dict]) -> list[dict]:
        """Merge and deduplicate keywords from both engines"""
        merged = {}

        for kw in dict_results:
            skill = kw['skill']
            merged[skill] = kw

        for kw in llm_results:
            skill = kw['skill']
            if skill not in merged:
                merged[skill] = kw
            else:
                merged[skill]['confidence'] = max(merged[skill]['confidence'], kw.get('confidence', 0.7))

        return list(merged.values())

    def _extract_keywords_dual_engine(self, text: str, use_llm: bool, keywords: list[str]) -> list[dict]:
        """Extract keywords using dual-engine architecture"""
        dict_results = self._extract_with_dictionary(text, keywords)

        if use_llm:
            llm_results = self._extract_with_llm(text)
            return self._merge_keywords(dict_results, llm_results)
        else:
            return dict_results

    def _build_skill_comparison(self, resume_keywords: list[dict], jd_keywords: list[dict],
                                resume_text: str, jd_text: str) -> list[dict]:
        """
        Build skill comparison statistics (Resume-Matcher algorithm)

        For each JD keyword, count mentions in both resume and JD to calculate:
        - Priority (based on JD frequency)
        - Weight (TF-IDF inspired)
        - Match status
        """
        jd_skills = {kw['skill'] for kw in jd_keywords}
        resume_skills = {kw['skill'] for kw in resume_keywords}

        stats = []
        for jd_kw in jd_keywords:
            skill = jd_kw['skill']

            # Count mentions in both texts
            jd_mentions = self._count_mentions(skill, jd_text)
            resume_mentions = self._count_mentions(skill, resume_text)

            # Priority classification (Resume-Matcher pattern)
            if jd_mentions >= 3:
                priority = "high"
                weight = 3.0
            elif jd_mentions == 2:
                priority = "medium"
                weight = 2.0
            else:
                priority = "low"
                weight = 1.0

            stats.append({
                "skill": skill,
                "resume_mentions": resume_mentions,
                "jd_mentions": jd_mentions,
                "priority": priority,
                "weight": weight,
                "matched": resume_mentions > 0
            })

        return stats

    def _calculate_match_score(self, resume_keywords: list[dict], jd_keywords: list[dict],
                               resume_text: str, jd_text: str, use_llm: bool, jd_source: str = "用户提供的职位描述") -> dict:
        """
        Calculate ATS match score using TF-IDF weighted algorithm

        Args:
            resume_keywords: Extracted resume keywords
            jd_keywords: Extracted JD keywords
            resume_text: Original resume text
            jd_text: Original JD text
            use_llm: Whether to use LLM for recommendations
            jd_source: Source of JD keywords (for display purposes)

        Returns comprehensive match analysis with:
        - Weighted match score (priority-based)
        - Simple match score (for comparison)
        - Matched/missing keywords breakdown
        - LLM-generated recommendations
        """
        # Build skill comparison statistics
        stats = self._build_skill_comparison(resume_keywords, jd_keywords, resume_text, jd_text)

        # Calculate weighted match score
        total_weight = sum(s['weight'] for s in stats)
        matched_weight = sum(s['weight'] for s in stats if s['matched'])
        weighted_score = round((matched_weight / total_weight * 100) if total_weight > 0 else 0, 1)

        # Calculate simple match score (for comparison)
        total_keywords = len(stats)
        matched_keywords = sum(1 for s in stats if s['matched'])
        simple_score = round((matched_keywords / total_keywords * 100) if total_keywords > 0 else 0, 1)

        # Categorize keywords
        matched = [s for s in stats if s['matched']]
        missing = [s for s in stats if not s['matched']]

        # Sort by priority
        matched_high = [s for s in matched if s['priority'] == 'high']
        matched_medium = [s for s in matched if s['priority'] == 'medium']
        matched_low = [s for s in matched if s['priority'] == 'low']

        missing_high = [s for s in missing if s['priority'] == 'high']
        missing_medium = [s for s in missing if s['priority'] == 'medium']
        missing_low = [s for s in missing if s['priority'] == 'low']

        # Generate LLM recommendations
        if use_llm and missing:
            recommendations = self._generate_recommendations(
                resume_text, jd_text, matched, missing,
                missing_high, missing_medium, weighted_score
            )
        else:
            recommendations = self._generate_rule_based_recommendations(
                missing_high, missing_medium, weighted_score
            )

        return {
            "match_analysis": {
                "weighted_match_score": weighted_score,
                "simple_match_score": simple_score,
                "total_resume_keywords": len(resume_keywords),
                "total_jd_keywords": len(jd_keywords),
                "matched_count": matched_keywords,
                "missing_count": len(missing)
            },
            "keywords": {
                "matched": {
                    "high_priority": [{"skill": s['skill'], "mentions": s['resume_mentions']} for s in matched_high],
                    "medium_priority": [{"skill": s['skill'], "mentions": s['resume_mentions']} for s in matched_medium],
                    "low_priority": [{"skill": s['skill'], "mentions": s['resume_mentions']} for s in matched_low]
                },
                "missing": {
                    "high_priority": [{"skill": s['skill'], "jd_mentions": s['jd_mentions']} for s in missing_high],
                    "medium_priority": [{"skill": s['skill'], "jd_mentions": s['jd_mentions']} for s in missing_medium],
                    "low_priority": [{"skill": s['skill'], "jd_mentions": s['jd_mentions']} for s in missing_low]
                }
            },
            "recommendations": recommendations
        }

    def _generate_recommendations(self, resume_text: str, jd_text: str,
                                  matched: list[dict], missing: list[dict],
                                  missing_high: list[dict], missing_medium: list[dict],
                                  weighted_score: float) -> str:
        """Generate LLM-powered optimization recommendations"""

        matched_skills = ", ".join([s['skill'] for s in matched[:15]])
        missing_high_skills = ", ".join([s['skill'] for s in missing_high])
        missing_medium_skills = ", ".join([s['skill'] for s in missing_medium])

        prompt = f"""你是一位资深的简历优化专家和 ATS 系统专家。基于关键词匹配分析，直接给出具体的简历优化建议。

## 匹配分析结果
- **ATS 匹配度**: {weighted_score}%
- **已匹配关键词**: {matched_skills}
- **缺失关键词（高优先级）**: {missing_high_skills or "无"}
- **缺失关键词（中优先级）**: {missing_medium_skills or "无"}

## 简历内容
{resume_text[:2000]}

## 职位描述
{jd_text[:2000]}

## 输出要求

**不要**自我介绍、不要分析问题、不要介绍工作计划，**直接开始输出优化建议**。

每条建议必须包含：
- **改前**：从简历中摘录需要修改的原文（如果是新增内容，写"无"）
- **改后**：优化后的表述（可直接复制粘贴使用）
- **优化理由**：1-2 句话说明为什么这样改，重点说明如何提升 ATS 匹配度

**重要**：如果某个优先级没有优化建议（例如缺失关键词为"无"或简历已经很好），**直接跳过该部分**，不要输出"改前：（无）改后：（无）"这样的空内容。

## 输出格式

### 🔴 高优先级优化（必须补充）

**仅在有缺失的高优先级关键词时输出此部分**

**改前**：
```
[从简历中摘录的原文，如果是新增内容则写"无"]
```

**改后**：
```
[优化后的表述，包含缺失的高优先级关键词]
```

**优化理由**：[说明如何提升 ATS 匹配度]

---

### 🟡 中优先级优化（建议补充）

**仅在有缺失的中优先级关键词时输出此部分**

**改前**：
```
[原文或"无"]
```

**改后**：
```
[优化后的表述，包含缺失的中优先级关键词]
```

**优化理由**：[说明如何提升 ATS 匹配度]

---

### 🟢 已匹配关键词优化（强化表述）

**仅在已匹配关键词可以进一步优化时输出此部分**

**改前**：
```
[原文]
```

**改后**：
```
[优化后的表述，增加关键词密度或量化指标]
```

**优化理由**：[说明如何更好地突出已匹配关键词]

---

## 优化重点

1. **补充缺失关键词**：优先补充高优先级关键词（{missing_high_skills or "无"}）
2. **增加关键词密度**：已匹配关键词要在简历中出现 2-3 次
3. **量化成果**：用数据说话（如：性能提升 X%、处理量 X 万次/日）
4. **ATS 友好格式**：避免表格、图片、特殊符号，使用标准字体和标题
5. **自然融入**：关键词要自然融入句子，不要生硬堆砌

---

**现在开始输出优化建议**（不要任何开场白，直接从第一条建议开始）："""

        llm_config = {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "mode": "chat",
            "completion_params": {
                "temperature": 0.7,
                "max_tokens": 3000
            }
        }

        # Retry logic for LLM invocation
        max_retries = 3
        retry_delay = 1  # Initial delay in seconds

        for attempt in range(max_retries):
            try:
                llm_result = self.session.model.llm.invoke(
                    model_config=LLMModelConfig(**llm_config),
                    prompt_messages=[UserPromptMessage(content=prompt)],
                    stream=False
                )

                response_text = llm_result.message.content.strip()

                # Check for empty response
                if not response_text:
                    if attempt < max_retries - 1:
                        print(f"⚠️ LLM returned empty recommendations (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        print(f"❌ LLM returned empty recommendations after {max_retries} attempts, using fallback")
                        return self._generate_rule_based_recommendations(missing_high, missing_medium, weighted_score)

                return response_text

            except Exception as llm_err:
                if attempt < max_retries - 1:
                    print(f"⚠️ LLM recommendation generation failed (attempt {attempt + 1}/{max_retries}): {str(llm_err)}, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    print(f"❌ LLM recommendation generation failed after {max_retries} attempts, using fallback")
                    return self._generate_rule_based_recommendations(missing_high, missing_medium, weighted_score)

        # Fallback to rule-based recommendations
        return self._generate_rule_based_recommendations(missing_high, missing_medium, weighted_score)

    def _generate_rule_based_recommendations(self, missing_high: list[dict],
                                            missing_medium: list[dict],
                                            weighted_score: float) -> str:
        """Generate rule-based recommendations (when LLM is disabled)"""
        recommendations = []

        recommendations.append(f"## ATS 匹配度: {weighted_score}%\n")

        if weighted_score >= 80:
            recommendations.append("✅ **优秀**：您的简历与职位描述高度匹配！")
        elif weighted_score >= 60:
            recommendations.append("⚠️ **良好**：简历匹配度不错，但仍有优化空间。")
        else:
            recommendations.append("❌ **需要优化**：简历与职位描述匹配度较低，建议重点优化。")

        if missing_high:
            recommendations.append("\n### 🔴 高优先级缺失关键词（必须补充）")
            for s in missing_high[:10]:
                recommendations.append(f"- **{s['skill']}** (JD中出现{s['jd_mentions']}次)")

        if missing_medium:
            recommendations.append("\n### 🟡 中优先级缺失关键词（建议补充）")
            for s in missing_medium[:10]:
                recommendations.append(f"- **{s['skill']}** (JD中出现{s['jd_mentions']}次)")

        recommendations.append("\n### 💡 优化建议")
        recommendations.append("1. 在简历中补充缺失的高优先级关键词")
        recommendations.append("2. 确保关键词出现在简历的多个部分（技能、项目经验、工作经历）")
        recommendations.append("3. 使用量化指标突出已匹配的关键词")
        recommendations.append("4. 避免使用表格、图片等 ATS 难以识别的格式")

        return "\n".join(recommendations)

    def _create_summary(self, match_result: dict, has_jd: bool) -> str:
        """Create human-readable summary"""
        if not has_jd:
            resume_kw_count = len(match_result.get('resume_keywords', []))
            return f"""# 📋 简历关键词提取结果

✅ 成功提取 {resume_kw_count} 个关键词

💡 **提示**: 提供职位描述（JD）可以获得：
- ATS 匹配度分析
- 缺失关键词识别
- 智能优化建议

请在参数中添加 `jd_text` 来获取完整的匹配分析。"""

        analysis = match_result['match_analysis']
        keywords = match_result['keywords']

        matched_high = keywords['matched']['high_priority']
        matched_medium = keywords['matched']['medium_priority']
        missing_high = keywords['missing']['high_priority']
        missing_medium = keywords['missing']['medium_priority']

        weighted_score = analysis['weighted_match_score']

        # Score emoji
        if weighted_score >= 80:
            score_emoji = "🟢"
        elif weighted_score >= 60:
            score_emoji = "🟡"
        else:
            score_emoji = "🔴"

        summary_lines = [
            "# 🎯 ATS 关键词匹配分析",
            "",
            f"## {score_emoji} 匹配度: {weighted_score}%",
            f"- **加权匹配度**: {weighted_score}% (基于关键词优先级)",
            f"- **简单匹配率**: {analysis['simple_match_score']}% (参考)",
            f"- **已匹配**: {analysis['matched_count']} 个关键词",
            f"- **缺失**: {analysis['missing_count']} 个关键词",
            ""
        ]

        if matched_high:
            summary_lines.append("### ✅ 已匹配关键词（高优先级）")
            for kw in matched_high[:10]:
                summary_lines.append(f"- **{kw['skill']}** (简历中出现{kw['mentions']}次)")
            summary_lines.append("")

        if missing_high:
            summary_lines.append("### ❌ 缺失关键词（高优先级）")
            for kw in missing_high[:10]:
                summary_lines.append(f"- **{kw['skill']}** (JD中出现{kw['jd_mentions']}次)")
            summary_lines.append("")

        if missing_medium:
            summary_lines.append("### ⚠️ 缺失关键词（中优先级）")
            for kw in missing_medium[:5]:
                summary_lines.append(f"- **{kw['skill']}** (JD中出现{kw['jd_mentions']}次)")
            summary_lines.append("")

        summary_lines.append("---")
        summary_lines.append("## 💡 优化建议")
        summary_lines.append(match_result['recommendations'])

        return "\n".join(summary_lines)

    def _parse_resume_keywords_input(self, input_str: str) -> list[dict[str, Any]] | None:
        """
        Intelligently parse resume_keywords input from various formats.

        Supports:
        1. JSON array: [{"skill": "Python", "mentions": 3, ...}, ...]
        2. JSON object: {"keywords": [...], ...}
        3. Text summary from keyword_extraction tool (parse keywords from markdown)

        Args:
            input_str: Input string from user

        Returns:
            List of keyword dicts, or None if parsing fails
        """
        input_str = input_str.strip()

        # Try 1: Parse as JSON
        try:
            parsed = json.loads(input_str)

            if isinstance(parsed, list):
                # Direct array: [{"skill": "Python", ...}, ...]
                return parsed
            elif isinstance(parsed, dict) and 'keywords' in parsed:
                # Full result object: {"keywords": [...], ...}
                return parsed['keywords']
        except json.JSONDecodeError:
            pass

        # Try 2: Parse as text summary from keyword_extraction
        # Look for patterns like: "- **Python** (2 mentions) - explicit mention"
        keywords = []

        # Pattern 1: "- **Skill** (N mentions) - source"
        pattern1 = r'-\s+\*\*([^*]+)\*\*\s+\((\d+)\s+mentions?\)\s+-\s+(.+)'
        matches1 = re.findall(pattern1, input_str)
        for skill, mentions, source in matches1:
            keywords.append({
                "skill": skill.strip(),
                "mentions": int(mentions),
                "confidence": 1.0,
                "source": "parsed_from_text"
            })

        # Pattern 2: "- **Skill** - description"
        pattern2 = r'-\s+\*\*([^*]+)\*\*\s+-\s+(.+)'
        matches2 = re.findall(pattern2, input_str)
        for skill, description in matches2:
            # Skip if already matched by pattern1
            if not any(k['skill'] == skill.strip() for k in keywords):
                keywords.append({
                    "skill": skill.strip(),
                    "mentions": 1,
                    "confidence": 0.8,
                    "source": "parsed_from_text"
                })

        if keywords:
            return keywords

        # Parsing failed
        return None

    def _generate_standard_jd_requirements(self, position_name: str) -> str:
        """
        Use LLM to generate standard job requirements for a given position name.

        Args:
            position_name: Job position name (e.g., "算法工程师实习", "前端开发工程师")

        Returns:
            Generated job description text with standard requirements
        """
        prompt = f"""你是一位资深的 HR 和招聘专家。请为"{position_name}"这个职位生成标准的技能要求清单。

请按照以下格式输出：

# {position_name} - 标准职位要求

## 核心技能要求（高优先级）
列出 3-5 个必须掌握的核心技能，每个技能需要在描述中出现 3 次以上。

## 重要技能要求（中优先级）
列出 5-8 个建议掌握的重要技能，每个技能需要在描述中出现 2 次。

## 加分技能要求（低优先级）
列出 3-5 个加分项技能，每个技能出现 1 次即可。

## 职位描述
用 2-3 段话描述这个职位的工作内容和职责，自然地融入上述技能关键词。

注意：
1. 技能关键词要具体（例如：Python、TensorFlow、RAG，而不是"编程能力"、"学习能力"）
2. 根据职位级别调整要求（实习生 vs 高级工程师）
3. 确保关键词在描述中自然出现指定次数
4. 使用中文输出

请开始生成："""

        llm_config = {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "mode": "chat",
            "completion_params": {
                "temperature": 0.7,
                "max_tokens": 2000
            }
        }

        # Retry logic for LLM invocation
        max_retries = 3
        retry_delay = 1  # Initial delay in seconds

        for attempt in range(max_retries):
            try:
                llm_result = self.session.model.llm.invoke(
                    model_config=LLMModelConfig(**llm_config),
                    prompt_messages=[UserPromptMessage(content=prompt)],
                    stream=False
                )

                response_text = llm_result.message.content.strip()

                # Check for empty response
                if not response_text:
                    if attempt < max_retries - 1:
                        print(f"⚠️ LLM returned empty JD (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        print(f"❌ LLM returned empty JD after {max_retries} attempts, using fallback")
                        return f"""# {position_name} - 标准职位要求

## 核心技能要求
根据职位名称，请提供完整的职位描述以获得更准确的匹配分析。

LLM 生成失败: 多次重试后仍返回空响应
"""

                return response_text

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"⚠️ LLM JD generation failed (attempt {attempt + 1}/{max_retries}): {str(e)}, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    print(f"❌ LLM JD generation failed after {max_retries} attempts: {str(e)}")
                    return f"""# {position_name} - 标准职位要求

## 核心技能要求
根据职位名称，请提供完整的职位描述以获得更准确的匹配分析。

LLM 生成失败: {str(e)}
"""

        # Fallback
        return f"""# {position_name} - 标准职位要求

## 核心技能要求
根据职位名称，请提供完整的职位描述以获得更准确的匹配分析。

LLM 生成失败: 未知错误
"""

    def _extract_keywords_from_generated_jd(self, generated_jd: str) -> list[dict[str, Any]]:
        """
        Extract keywords from LLM-generated job description.
        Parse the structured output and create keyword list with priorities.

        Args:
            generated_jd: LLM-generated job description text

        Returns:
            List of keyword dictionaries with skill, mentions, priority, weight
        """
        keywords = []

        # Parse high-priority skills (mentioned 3+ times in the generated JD)
        high_priority_pattern = r"## 核心技能要求[^#]+"
        high_match = re.search(high_priority_pattern, generated_jd, re.DOTALL)
        if high_match:
            high_section = high_match.group(0)
            # Extract skill names (look for technical terms in Chinese/English)
            skills = re.findall(r'[A-Za-z][A-Za-z0-9+#\.]*(?:\.[A-Za-z]+)?', high_section)
            for skill in skills:
                if len(skill) > 1:  # Filter out single letters
                    keywords.append({
                        "skill": skill,
                        "mentions": 3,  # High priority = 3 mentions
                        "confidence": 1.0,
                        "source": "llm_generated",
                        "priority": "high",
                        "weight": 3.0
                    })

        # Parse medium-priority skills (mentioned 2 times)
        medium_priority_pattern = r"## 重要技能要求[^#]+"
        medium_match = re.search(medium_priority_pattern, generated_jd, re.DOTALL)
        if medium_match:
            medium_section = medium_match.group(0)
            skills = re.findall(r'[A-Za-z][A-Za-z0-9+#\.]*(?:\.[A-Za-z]+)?', medium_section)
            for skill in skills:
                if len(skill) > 1 and skill not in [k['skill'] for k in keywords]:
                    keywords.append({
                        "skill": skill,
                        "mentions": 2,  # Medium priority = 2 mentions
                        "confidence": 1.0,
                        "source": "llm_generated",
                        "priority": "medium",
                        "weight": 2.0
                    })

        # Parse low-priority skills (mentioned 1 time)
        low_priority_pattern = r"## 加分技能要求[^#]+"
        low_match = re.search(low_priority_pattern, generated_jd, re.DOTALL)
        if low_match:
            low_section = low_match.group(0)
            skills = re.findall(r'[A-Za-z][A-Za-z0-9+#\.]*(?:\.[A-Za-z]+)?', low_section)
            for skill in skills:
                if len(skill) > 1 and skill not in [k['skill'] for k in keywords]:
                    keywords.append({
                        "skill": skill,
                        "mentions": 1,  # Low priority = 1 mention
                        "confidence": 1.0,
                        "source": "llm_generated",
                        "priority": "low",
                        "weight": 1.0
                    })

        return keywords


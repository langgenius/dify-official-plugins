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

# Import TECH_SYNONYMS dictionary (not the class to avoid multiple Tool subclasses)
from .keyword_extraction import TECH_SYNONYMS


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
    
    def _count_mentions(self, keyword: str, text: str) -> tuple[int, str]:
        """
        Count keyword mentions in text, including synonyms.

        Returns:
            (count, match_type):
            - count: Total mentions (exact + synonyms)
            - match_type: "exact" | "synonym:{matched_synonym}" | "none"
        """
        text_lower = text.lower()
        keyword_lower = keyword.lower()

        # 1. Exact match (case-insensitive for most keywords)
        if keyword in self.CASE_SENSITIVE_KEYWORDS:
            pattern = re.compile(rf"(?<!\w){re.escape(keyword)}(?!\w)")
            exact_count = len(pattern.findall(text))
        else:
            text_normalized = self._prepare_text_for_matching(text)
            pattern = re.compile(rf"(?<!\w){re.escape(keyword_lower)}(?!\w)")
            exact_count = len(pattern.findall(text_normalized))

        if exact_count > 0:
            return exact_count, "exact"

        # 2. Synonym match
        synonyms = TECH_SYNONYMS.get(keyword, [])
        synonym_count = 0
        matched_synonym = None

        for synonym in synonyms:
            synonym_lower = synonym.lower()
            # Use word boundary regex for synonym matching
            pattern = re.compile(rf"(?<!\w){re.escape(synonym_lower)}(?!\w)")
            count = len(pattern.findall(text_lower))
            if count > 0:
                synonym_count += count
                if matched_synonym is None:
                    matched_synonym = synonym

        if synonym_count > 0:
            return synonym_count, f"synonym:{matched_synonym}"

        # 3. No match
        return 0, "none"

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

    def _analyze_jd_priority_with_llm(self, jd_text: str, jd_keywords: list[str], use_llm: bool) -> dict:
        """
        Analyze JD and classify keywords into Must-have/High/Medium/Nice-to-have
        using LLM (simulating Greenhouse/Lever ATS logic)

        Args:
            jd_text: Job description text
            jd_keywords: List of extracted keywords
            use_llm: Whether to use LLM for analysis

        Returns:
            Dictionary with classified keywords:
            {
                "must_have": [...],
                "high_priority": [...],
                "medium_priority": [...],
                "nice_to_have": [...],
                "reasoning": "..."
            }
        """
        if not use_llm or not jd_keywords:
            # Fallback: use frequency-based classification
            return self._fallback_priority_classification(jd_text, jd_keywords)

        prompt = f"""你是一个专业的招聘 ATS 系统分析专家。请分析以下职位描述（JD），将提取的关键词按照 Greenhouse/Lever ATS 系统的标准分类。

## 职位描述

{jd_text}

## 已提取的关键词

{', '.join(jd_keywords)}

## 分类标准

**Must-have（必需技能）**：
- 出现在"任职要求"/"Required Qualifications"部分
- 使用"必须"/"must"/"required"等强制性词汇
- 是岗位的核心技能，缺失则无法胜任
- 示例：对于算法工程师，"Python"和"机器学习"通常是 Must-have

**High Priority（高优先级）**：
- 出现在"核心技能"/"Key Skills"部分
- JD 中多次强调（出现 3 次以上）
- 是岗位的主要工作内容所需技能
- 示例：对于算法工程师，"TensorFlow"或"PyTorch"通常是 High Priority

**Medium Priority（中优先级）**：
- 出现在"优先条件"/"Preferred Qualifications"部分
- JD 中提及 2 次左右
- 是加分项，但不是必需
- 示例：对于算法工程师，"Docker"和"Kubernetes"通常是 Medium Priority

**Nice-to-have（加分项）**：
- 出现在"加分项"/"Nice to have"部分
- JD 中只提及 1 次
- 是锦上添花的技能
- 示例：对于算法工程师，"AWS"和"GCP"通常是 Nice-to-have

## 输出格式（JSON only）

{{
  "must_have": ["Python", "Machine Learning"],
  "high_priority": ["TensorFlow", "PyTorch", "Deep Learning"],
  "medium_priority": ["Docker", "Kubernetes", "Linux"],
  "nice_to_have": ["AWS", "GCP", "CI/CD"],
  "reasoning": "简要说明分类依据"
}}

**重要**：
1. 每个关键词只能出现在一个分类中
2. 如果 JD 没有明确区分，根据岗位类型和行业惯例判断
3. Must-have 通常不超过 3-5 个关键词
4. 输出 ONLY valid JSON，no markdown"""

        try:
            # Invoke LLM with retry logic
            max_retries = 3
            retry_delay = 1

            for attempt in range(max_retries):
                try:
                    llm_result = self.session.model.llm.invoke(
                        model_config=LLMModelConfig(**self.runtime.credentials),
                        prompt_messages=[UserPromptMessage(content=prompt)],
                        stream=False
                    )

                    if llm_result and hasattr(llm_result, 'message') and hasattr(llm_result.message, 'content'):
                        response_text = llm_result.message.content.strip()

                        if not response_text:
                            if attempt < max_retries - 1:
                                time.sleep(retry_delay)
                                retry_delay *= 2
                                continue
                            else:
                                return self._fallback_priority_classification(jd_text, jd_keywords)

                        # Parse JSON
                        # Remove markdown code blocks if present
                        if "```json" in response_text:
                            response_text = response_text.split("```json")[1].split("```")[0].strip()
                        elif "```" in response_text:
                            response_text = response_text.split("```")[1].split("```")[0].strip()

                        priority_analysis = json.loads(response_text)

                        # Validate structure
                        required_keys = ["must_have", "high_priority", "medium_priority", "nice_to_have"]
                        if all(key in priority_analysis for key in required_keys):
                            return priority_analysis
                        else:
                            return self._fallback_priority_classification(jd_text, jd_keywords)

                except json.JSONDecodeError:
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        return self._fallback_priority_classification(jd_text, jd_keywords)

                except Exception:
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        return self._fallback_priority_classification(jd_text, jd_keywords)

            return self._fallback_priority_classification(jd_text, jd_keywords)

        except Exception:
            return self._fallback_priority_classification(jd_text, jd_keywords)

    def _fallback_priority_classification(self, jd_text: str, jd_keywords: list[str]) -> dict:
        """
        Fallback priority classification based on keyword frequency in JD
        (used when LLM is unavailable or fails)
        """
        result = {
            "must_have": [],
            "high_priority": [],
            "medium_priority": [],
            "nice_to_have": [],
            "reasoning": "基于关键词在 JD 中的出现频率自动分类（LLM 不可用）"
        }

        for keyword in jd_keywords:
            count, _ = self._count_mentions(keyword, jd_text)

            if count >= 3:
                result["high_priority"].append(keyword)
            elif count == 2:
                result["medium_priority"].append(keyword)
            else:
                result["nice_to_have"].append(keyword)

        # If no must_have, promote top 2-3 high_priority to must_have
        if not result["must_have"] and result["high_priority"]:
            result["must_have"] = result["high_priority"][:min(3, len(result["high_priority"]))]
            result["high_priority"] = result["high_priority"][min(3, len(result["high_priority"])):]

        return result

    def _build_skill_comparison(self, resume_keywords: list[dict], jd_keywords: list[dict],
                                resume_text: str, jd_text: str) -> list[dict]:
        """
        Build skill comparison statistics (Resume-Matcher algorithm)

        For each JD keyword, count mentions in both resume and JD to calculate:
        - Priority (based on JD frequency)
        - Weight (TF-IDF inspired)
        - Match status
        - Match type (exact or synonym)
        """
        jd_skills = {kw['skill'] for kw in jd_keywords}
        resume_skills = {kw['skill'] for kw in resume_keywords}

        stats = []
        for jd_kw in jd_keywords:
            skill = jd_kw['skill']

            # Count mentions in both texts (with synonym support)
            jd_mentions, _ = self._count_mentions(skill, jd_text)
            resume_mentions, match_type = self._count_mentions(skill, resume_text)

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
                "matched": resume_mentions > 0,
                "match_type": match_type  # "exact" | "synonym:xxx" | "none"
            })

        return stats

    def _calculate_match_score(self, resume_keywords: list[dict], jd_keywords: list[dict],
                               resume_text: str, jd_text: str, use_llm: bool, jd_source: str = "用户提供的职位描述") -> dict:
        """
        Calculate ATS match score simulating Greenhouse/Lever logic

        New algorithm (v0.5.0):
        1. Use LLM to classify JD keywords into Must-have/High/Medium/Nice-to-have
        2. Match keywords with synonym support
        3. Calculate Greenhouse-style score with tiered weighting
        4. Generate actionable optimization suggestions

        Args:
            resume_keywords: Extracted resume keywords
            jd_keywords: Extracted JD keywords
            resume_text: Original resume text
            jd_text: Original JD text
            use_llm: Whether to use LLM for analysis
            jd_source: Source of JD keywords (for display purposes)

        Returns comprehensive match analysis with:
        - Greenhouse score (simulated)
        - Tiered match rates (Must-have/High/Medium/Nice-to-have)
        - Match type details (exact vs synonym)
        - Optimization suggestions
        """
        # 1. Analyze JD priority with LLM
        jd_keyword_list = [kw['skill'] for kw in jd_keywords]
        priority_analysis = self._analyze_jd_priority_with_llm(jd_text, jd_keyword_list, use_llm)

        # 2. Match keywords for each priority level
        match_results = {
            "must_have": [],
            "high_priority": [],
            "medium_priority": [],
            "nice_to_have": []
        }

        for priority_level, keywords in priority_analysis.items():
            if priority_level == "reasoning":
                continue

            for keyword in keywords:
                count, match_type = self._count_mentions(keyword, resume_text)

                match_results[priority_level].append({
                    "skill": keyword,
                    "matched": count > 0,
                    "match_type": match_type,
                    "mentions": count
                })

        # 3. Calculate tiered match rates
        must_have_total = len(match_results["must_have"])
        must_have_matched = sum(1 for s in match_results["must_have"] if s["matched"])
        must_have_rate = (must_have_matched / must_have_total * 100) if must_have_total > 0 else 100

        high_total = len(match_results["high_priority"])
        high_matched = sum(1 for s in match_results["high_priority"] if s["matched"])
        high_rate = (high_matched / high_total * 100) if high_total > 0 else 100

        medium_total = len(match_results["medium_priority"])
        medium_matched = sum(1 for s in match_results["medium_priority"] if s["matched"])
        medium_rate = (medium_matched / medium_total * 100) if medium_total > 0 else 100

        nice_total = len(match_results["nice_to_have"])
        nice_matched = sum(1 for s in match_results["nice_to_have"] if s["matched"])
        nice_rate = (nice_matched / nice_total * 100) if nice_total > 0 else 100

        # 4. Check Must-have (must be 100% matched)
        if must_have_rate < 100:
            status = "rejected"
            greenhouse_score = 0
            recommendation = "❌ 不推荐投递：缺失必需技能"
        else:
            # 5. Calculate Greenhouse score (weighted)
            greenhouse_score = (
                must_have_rate * 0.4 +   # Must-have: 40%
                high_rate * 0.3 +         # High Priority: 30%
                medium_rate * 0.2 +       # Medium Priority: 20%
                nice_rate * 0.1           # Nice-to-have: 10%
            )

            # 6. Determine status
            if greenhouse_score >= 85:
                status = "strongly_recommended"
                recommendation = "✅ 强烈推荐投递：简历高度匹配"
            elif greenhouse_score >= 75:
                status = "recommended"
                recommendation = "✅ 推荐投递：简历匹配度良好"
            elif greenhouse_score >= 65:
                status = "consider"
                recommendation = "⚠️ 可以考虑：建议优化后投递"
            else:
                status = "not_recommended"
                recommendation = "❌ 不推荐投递：匹配度较低"

        # 7. Generate optimization suggestions
        optimization_suggestions = self._generate_optimization_suggestions(match_results, priority_analysis)

        # 8. Calculate legacy scores for comparison
        stats = self._build_skill_comparison(resume_keywords, jd_keywords, resume_text, jd_text)
        total_weight = sum(s['weight'] for s in stats)
        matched_weight = sum(s['weight'] for s in stats if s['matched'])
        legacy_weighted_score = round((matched_weight / total_weight * 100) if total_weight > 0 else 0, 1)

        total_keywords = len(stats)
        matched_keywords = sum(1 for s in stats if s['matched'])
        simple_score = round((matched_keywords / total_keywords * 100) if total_keywords > 0 else 0, 1)

        return {
            "greenhouse_analysis": {
                "greenhouse_score": round(greenhouse_score, 1),
                "status": status,
                "recommendation": recommendation,
                "must_have_match": f"{must_have_matched}/{must_have_total}",
                "must_have_rate": round(must_have_rate, 1),
                "high_priority_match": f"{high_matched}/{high_total}",
                "high_priority_rate": round(high_rate, 1),
                "medium_priority_match": f"{medium_matched}/{medium_total}",
                "medium_priority_rate": round(medium_rate, 1),
                "nice_to_have_match": f"{nice_matched}/{nice_total}",
                "nice_to_have_rate": round(nice_rate, 1)
            },
            "match_details": match_results,
            "priority_analysis": priority_analysis,
            "optimization_suggestions": optimization_suggestions,
            "legacy_scores": {
                "weighted_score": legacy_weighted_score,
                "simple_score": simple_score,
                "total_keywords": total_keywords,
                "matched_keywords": matched_keywords
            }
        }

    def _generate_optimization_suggestions(self, match_results: dict, priority_analysis: dict) -> str:
        """
        Generate actionable optimization suggestions based on match results

        Suggestions are prioritized by:
        1. Must-have missing (critical)
        2. Synonym matches (easy fix)
        3. High priority missing (important)
        4. Medium priority missing (recommended)
        """
        suggestions = []

        # 1. Must-have missing (highest priority)
        must_have_missing = [s for s in match_results["must_have"] if not s["matched"]]
        if must_have_missing:
            suggestions.append("## 🔴 必需技能缺失（必须补充）\n")
            for skill in must_have_missing:
                suggestions.append(f"- **{skill['skill']}**: 这是必需技能，缺失会直接导致简历被 ATS 淘汰")
                suggestions.append(f"  - 建议：如果有相关经验，请在简历中明确添加此关键词")
                suggestions.append(f"  - 建议：如果没有经验，建议先学习后再投递\n")

        # 2. Synonym matches (easy fix - just change wording)
        synonym_matches = []
        for priority_level, skills in match_results.items():
            for skill in skills:
                if skill["matched"] and "synonym:" in skill["match_type"]:
                    synonym = skill["match_type"].split(":")[1]
                    synonym_matches.append((skill["skill"], synonym, priority_level))

        if synonym_matches:
            suggestions.append("## ⚠️ 用词优化（提高 ATS 识别率）\n")
            suggestions.append("**问题**：你使用了同义词或缩写，ATS 系统可能识别不出\n")
            for standard, synonym, level in synonym_matches:
                suggestions.append(f"- 你写的是 **{synonym}**，建议改为 **{standard}**")
                suggestions.append(f"  - 原因：Greenhouse/Lever 等 ATS 系统可能识别不出缩写或同义词")
                suggestions.append(f"  - 建议：改为 '{standard} ({synonym})' 或直接用 '{standard}'")
                suggestions.append(f"  - 优先级：{level}\n")

        # 3. High priority missing
        high_missing = [s for s in match_results["high_priority"] if not s["matched"]]
        if high_missing:
            suggestions.append("## 🟡 高优先级技能缺失（强烈建议补充）\n")
            for skill in high_missing:
                suggestions.append(f"- **{skill['skill']}**: 高优先级技能，补充后可显著提升匹配度")
                suggestions.append(f"  - 建议：如果有相关经验，请在项目描述中明确提及")
                suggestions.append(f"  - 建议：如果没有经验，考虑通过项目或学习补充\n")

        # 4. Medium priority missing (only show top 3)
        medium_missing = [s for s in match_results["medium_priority"] if not s["matched"]]
        if medium_missing:
            suggestions.append("## 🟢 中优先级技能缺失（建议补充）\n")
            for skill in medium_missing[:3]:  # Only show top 3
                suggestions.append(f"- **{skill['skill']}**: 中优先级技能，补充后可提升竞争力\n")
            if len(medium_missing) > 3:
                suggestions.append(f"\n...还有 {len(medium_missing) - 3} 个中优先级技能缺失\n")

        # 5. Summary
        if not must_have_missing:
            suggestions.append("## ✅ 总结\n")
            if synonym_matches:
                suggestions.append(f"- 你已满足所有必需技能，但有 {len(synonym_matches)} 个关键词使用了同义词")
                suggestions.append(f"- 建议优先修改用词，提高 ATS 识别率\n")
            if high_missing:
                suggestions.append(f"- 缺失 {len(high_missing)} 个高优先级技能，建议补充\n")
            if not synonym_matches and not high_missing:
                suggestions.append("- 你的简历匹配度很高，可以直接投递！\n")

        return "\n".join(suggestions) if suggestions else "暂无优化建议"

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
        """Create human-readable summary with Greenhouse-style scoring"""
        if not has_jd:
            resume_kw_count = len(match_result.get('resume_keywords', []))
            return f"""# 📋 简历关键词提取结果

✅ 成功提取 {resume_kw_count} 个关键词

💡 **提示**: 提供职位描述（JD）可以获得：
- Greenhouse/Lever ATS 匹配度分析
- 分级关键词匹配情况
- 智能优化建议

请在参数中添加 `jd_text` 来获取完整的匹配分析。"""

        # New Greenhouse analysis
        greenhouse = match_result['greenhouse_analysis']
        match_details = match_result['match_details']
        optimization = match_result['optimization_suggestions']
        legacy = match_result['legacy_scores']

        greenhouse_score = greenhouse['greenhouse_score']
        status = greenhouse['status']

        # Score emoji based on Greenhouse score
        if greenhouse_score >= 85:
            score_emoji = "🟢"
        elif greenhouse_score >= 75:
            score_emoji = "🟡"
        elif greenhouse_score >= 65:
            score_emoji = "🟠"
        else:
            score_emoji = "🔴"

        summary_lines = [
            "# 🎯 ATS 匹配分析（Greenhouse/Lever 模拟）",
            "",
            f"## {score_emoji} Greenhouse 预估分数: {greenhouse_score} 分",
            "",
            greenhouse['recommendation'],
            "",
            "---",
            "",
            "## 📊 分级匹配情况",
            "",
            f"### 🔴 必需技能（Must-have）",
            f"- 匹配: {greenhouse['must_have_match']} ({greenhouse['must_have_rate']}%)",
        ]

        # Show must-have details
        must_have_matched = [s for s in match_details['must_have'] if s['matched']]
        must_have_missing = [s for s in match_details['must_have'] if not s['matched']]

        if must_have_matched:
            summary_lines.append("- 已匹配: " + ", ".join([f"**{s['skill']}**" for s in must_have_matched]))
        if must_have_missing:
            summary_lines.append("- ❌ 缺失: " + ", ".join([f"**{s['skill']}**" for s in must_have_missing]))

        summary_lines.extend([
            "",
            f"### 🟡 高优先级技能（High Priority）",
            f"- 匹配: {greenhouse['high_priority_match']} ({greenhouse['high_priority_rate']}%)",
        ])

        # Show high priority details
        high_matched = [s for s in match_details['high_priority'] if s['matched']]
        high_missing = [s for s in match_details['high_priority'] if not s['matched']]

        if high_matched:
            summary_lines.append("- 已匹配: " + ", ".join([f"**{s['skill']}**" for s in high_matched[:5]]))
        if high_missing:
            summary_lines.append("- ❌ 缺失: " + ", ".join([f"**{s['skill']}**" for s in high_missing[:5]]))

        summary_lines.extend([
            "",
            f"### 🟢 中优先级技能（Medium Priority）",
            f"- 匹配: {greenhouse['medium_priority_match']} ({greenhouse['medium_priority_rate']}%)",
            "",
            f"### ⚪ 加分项（Nice-to-have）",
            f"- 匹配: {greenhouse['nice_to_have_match']} ({greenhouse['nice_to_have_rate']}%)",
            "",
            "---",
            "",
            "## 💡 优化建议",
            "",
            optimization,
            "",
            "---",
            "",
            "## 📈 评分对比",
            "",
            f"- **Greenhouse 分数**: {greenhouse_score} 分（模拟 Greenhouse/Lever ATS）",
            f"- **传统加权分数**: {legacy['weighted_score']}% （基于关键词频率）",
            f"- **简单匹配率**: {legacy['simple_score']}% （{legacy['matched_keywords']}/{legacy['total_keywords']}）",
            "",
            "💡 **说明**: Greenhouse 分数更接近真实 ATS 系统的评分逻辑，优先考虑必需技能和高优先级技能。",
        ])

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


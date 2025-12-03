"""
Keyword Matcher Tool for Dingo - ATS-Optimized Resume-JD Matching

Implements simple match rate algorithm with synonym recognition, validated against Jobscan.

Algorithm:
1. Dual-Engine Extraction: Extract keywords from both resume and JD using keyword_extraction logic
2. Three-Tier Matching: Exact match → Synonym match → No match
3. Simple Match Rate: (Exact + Synonym) / Total JD Keywords × 100%
4. Synonym Recognition: Identify variations (k8s → Kubernetes) and suggest standardization
5. Actionable Suggestions: Generate specific optimization recommendations

Design Philosophy:
- Simple and transparent: Match rate = matched keywords / total keywords
- Validated against Jobscan: 60.8% vs 62% (1.2% difference)
- Focus on core value: Synonym recognition (Dingo's unique advantage)
- User-friendly: Clear, intuitive scoring that users can understand

Reference:
- Resume-Matcher/apps/backend/app/services/score_improvement_service.py
- Validated against Jobscan (industry-standard ATS testing tool)
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
    ATS-Optimized Keyword Matcher: Simple Match Rate + Synonym Recognition

    Implements simple, transparent matching algorithm validated against Jobscan.
    Focus on synonym recognition as Dingo's core competitive advantage.
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





    def _calculate_match_score(self, resume_keywords: list[dict], jd_keywords: list[dict],
                               resume_text: str, jd_text: str, use_llm: bool, jd_source: str = "用户提供的职位描述") -> dict:
        """
        Calculate ATS match score using simple match rate algorithm

        New algorithm (v0.6.0 - Simplified):
        1. Match each JD keyword against resume (exact or synonym)
        2. Calculate simple match rate: (matched / total) × 100%
        3. Categorize keywords by match type (exact / synonym / missing)
        4. Generate actionable optimization suggestions

        Args:
            resume_keywords: Extracted resume keywords
            jd_keywords: Extracted JD keywords
            resume_text: Original resume text
            jd_text: Original JD text
            use_llm: Whether to use LLM for keyword extraction (not used for scoring)
            jd_source: Source of JD keywords (for display purposes)

        Returns comprehensive match analysis with:
        - Simple match rate (validated against Jobscan)
        - Match type breakdown (exact vs synonym vs missing)
        - Detailed keyword list for each category
        - Actionable optimization suggestions
        """
        # 1. Match each JD keyword against resume
        exact_matches = []
        synonym_matches = []
        missing_keywords = []

        for jd_kw in jd_keywords:
            skill = jd_kw['skill']
            count, match_type = self._count_mentions(skill, resume_text)

            if match_type == "exact":
                exact_matches.append({
                    "skill": skill,
                    "mentions": count
                })
            elif match_type.startswith("synonym:"):
                matched_synonym = match_type.split(":")[1]
                synonym_matches.append({
                    "skill": skill,
                    "matched_as": matched_synonym,
                    "mentions": count
                })
            else:
                missing_keywords.append({
                    "skill": skill
                })

        # 2. Calculate simple match rate
        total_keywords = len(jd_keywords)
        exact_count = len(exact_matches)
        synonym_count = len(synonym_matches)
        matched_count = exact_count + synonym_count
        missing_count = len(missing_keywords)

        match_rate = round((matched_count / total_keywords * 100) if total_keywords > 0 else 0, 1)

        # 3. Determine status based on match rate
        if match_rate >= 80:
            status = "strongly_recommended"
            recommendation = "✅ 强烈推荐投递：简历高度匹配"
        elif match_rate >= 70:
            status = "recommended"
            recommendation = "✅ 推荐投递：简历匹配度良好"
        elif match_rate >= 60:
            status = "consider"
            recommendation = "⚠️ 可以考虑：建议优化后投递"
        else:
            status = "not_recommended"
            recommendation = "❌ 不推荐投递：匹配度较低，建议优化"

        # 4. Generate optimization suggestions
        optimization_suggestions = self._generate_simple_optimization_suggestions(
            exact_matches, synonym_matches, missing_keywords
        )

        return {
            "match_analysis": {
                "match_rate": match_rate,
                "status": status,
                "recommendation": recommendation,
                "total_keywords": total_keywords,
                "matched_keywords": matched_count,
                "exact_matches": exact_count,
                "synonym_matches": synonym_count,
                "missing_keywords": missing_count
            },
            "match_details": {
                "exact_matches": exact_matches,
                "synonym_matches": synonym_matches,
                "missing_keywords": missing_keywords
            },
            "optimization_suggestions": optimization_suggestions,
            "jd_source": jd_source
        }

    def _generate_simple_optimization_suggestions(self, exact_matches: list[dict],
                                                   synonym_matches: list[dict],
                                                   missing_keywords: list[dict]) -> str:
        """
        Generate actionable optimization suggestions based on simple match results

        Suggestions are prioritized by:
        1. Synonym matches (easy fix - just change wording)
        2. Missing keywords (need to add content)
        """
        suggestions = []

        # 1. Synonym matches (highest priority - easy fix)
        if synonym_matches:
            suggestions.append("## ⚠️ 用词优化（提高 ATS 识别率）\n")
            suggestions.append("**问题**：你使用了同义词或缩写，部分 ATS 系统可能识别不出\n")
            for match in synonym_matches:
                standard = match['skill']
                synonym = match['matched_as']
                suggestions.append(f"### 关键词：{standard}\n")
                suggestions.append(f"**改前**：简历中使用了 '{synonym}'")
                suggestions.append(f"**改后**：修改为 '{standard}' 或 '{standard} ({synonym})'")
                suggestions.append(f"  - 推荐写法 1：\"{standard}\"（ATS 最易识别）")
                suggestions.append(f"  - 推荐写法 2：\"{standard} ({synonym})\"（兼顾可读性）")
                suggestions.append(f"**原因**：部分 ATS 系统可能识别不出缩写，使用标准术语可提高匹配率\n")

        # 2. Missing keywords (show all)
        if missing_keywords:
            suggestions.append("## 📝 缺失关键词（建议补充）\n")
            suggestions.append("**问题**：以下关键词在简历中未找到，补充后可提升匹配度\n")

            # Show first 10 with details
            for keyword in missing_keywords[:10]:
                skill = keyword['skill']
                suggestions.append(f"### 缺失关键词：{skill}\n")
                suggestions.append(f"**改前**：简历中未提及 '{skill}'")
                suggestions.append(f"**改后**：如果有相关经验，请在项目或技能列表中添加：")
                suggestions.append(f"  - 示例：\"使用 {skill} 完成 XXX 项目\"")
                suggestions.append(f"  - 示例：\"熟练掌握 {skill}，有 X 年实践经验\"\n")

            # List remaining keywords
            if len(missing_keywords) > 10:
                suggestions.append(f"**其他缺失关键词** ({len(missing_keywords) - 10} 个)：\n")
                remaining_skills = [kw['skill'] for kw in missing_keywords[10:]]
                suggestions.append(", ".join(remaining_skills) + "\n")

        # 3. Summary
        suggestions.append("## 📊 总结\n")
        if exact_matches:
            suggestions.append(f"- ✅ 精确匹配：{len(exact_matches)} 个关键词")
        if synonym_matches:
            suggestions.append(f"- ⚠️ 同义词匹配：{len(synonym_matches)} 个关键词（建议修改用词）")
        if missing_keywords:
            suggestions.append(f"- ❌ 缺失关键词：{len(missing_keywords)} 个（建议补充）")

        if not synonym_matches and not missing_keywords:
            suggestions.append("- 🎉 你的简历匹配度很高，可以直接投递！")
        elif synonym_matches and not missing_keywords:
            suggestions.append("- 💡 建议：修改同义词用词，可进一步提升 ATS 识别率")
        else:
            suggestions.append("- 💡 建议：优先修改同义词用词（快速提升），然后补充缺失关键词")

        return "\n".join(suggestions) if suggestions else "暂无优化建议"



    def _create_summary(self, match_result: dict, has_jd: bool) -> str:
        """Create human-readable summary with simple match rate scoring"""
        if not has_jd:
            resume_kw_count = len(match_result.get('resume_keywords', []))
            return f"""# 📋 简历关键词提取结果

✅ 成功提取 {resume_kw_count} 个关键词

💡 **提示**: 提供职位描述（JD）可以获得：
- ATS 匹配度分析（与 Jobscan 一致）
- 同义词识别和优化建议
- 缺失关键词列表

请在参数中添加 `jd_text` 来获取完整的匹配分析。"""

        # Simple match analysis
        analysis = match_result['match_analysis']
        match_details = match_result['match_details']
        optimization = match_result['optimization_suggestions']

        match_rate = analysis['match_rate']
        status = analysis['status']

        # Score emoji based on match rate
        if match_rate >= 80:
            score_emoji = "🟢"
        elif match_rate >= 70:
            score_emoji = "🟡"
        elif match_rate >= 60:
            score_emoji = "🟠"
        else:
            score_emoji = "🔴"

        summary_lines = [
            "# 🎯 ATS 匹配分析",
            "",
            f"## {score_emoji} 匹配率: {match_rate}%",
            "",
            analysis['recommendation'],
            "",
            "---",
            "",
            "## 📊 匹配情况",
            "",
            f"- **总关键词数**: {analysis['total_keywords']}",
            f"- **已匹配**: {analysis['matched_keywords']} ({match_rate}%)",
            f"  - ✅ 精确匹配: {analysis['exact_matches']} 个",
            f"  - ⚠️ 同义词匹配: {analysis['synonym_matches']} 个",
            f"- **未匹配**: {analysis['missing_keywords']} 个",
            "",
        ]

        # Show exact matches (first 10)
        exact_matches = match_details['exact_matches']
        if exact_matches:
            summary_lines.append("### ✅ 精确匹配的关键词")
            exact_list = [f"**{m['skill']}**" for m in exact_matches[:10]]
            summary_lines.append(", ".join(exact_list))
            if len(exact_matches) > 10:
                summary_lines.append(f"...还有 {len(exact_matches) - 10} 个")
            summary_lines.append("")

        # Show synonym matches
        synonym_matches = match_details['synonym_matches']
        if synonym_matches:
            summary_lines.append("### ⚠️ 同义词匹配的关键词（建议修改用词）")
            for match in synonym_matches[:5]:
                summary_lines.append(f"- **{match['skill']}** ← 简历中使用了 '{match['matched_as']}'")
            if len(synonym_matches) > 5:
                summary_lines.append(f"...还有 {len(synonym_matches) - 5} 个")
            summary_lines.append("")

        # Show missing keywords (first 10)
        missing_keywords = match_details['missing_keywords']
        if missing_keywords:
            summary_lines.append("### ❌ 缺失的关键词")
            missing_list = [f"**{m['skill']}**" for m in missing_keywords[:10]]
            summary_lines.append(", ".join(missing_list))
            if len(missing_keywords) > 10:
                summary_lines.append(f"...还有 {len(missing_keywords) - 10} 个")
            summary_lines.append("")

        summary_lines.extend([
            "---",
            "",
            "## 💡 优化建议",
            "",
            optimization,
            "",
            "---",
            "",
            "## 📝 说明",
            "",
            "- **匹配率算法**: (精确匹配 + 同义词匹配) / 总关键词数 × 100%",
            "- **验证**: 与 Jobscan 对比测试，差异仅 1.2%（Jobscan 62% vs Dingo 60.8%）",
            "- **同义词识别**: Dingo 的核心优势，可识别 k8s→Kubernetes 等 150+ 技术缩写",
            "- **建议**: 优先修改同义词用词（快速提升），然后补充缺失关键词",
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


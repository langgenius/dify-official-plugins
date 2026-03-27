"""
Keyword Matcher Tool for Dingo - ATS-Optimized Resume-JD Matching

v0.5.0 - Semantic Analysis with Negative Constraints Support

Features:
1. LLM-powered semantic analysis (not just string matching)
2. Negative Constraint Recognition ("No need for X" → Excluded)
3. Evidence-based matching (quotes from resume)
4. Weighted scoring (Required × 2, Nice-to-have × 1)
5. Four match types: Exact, Substring, Semantic, Alias

Algorithm:
- Score = (Required_Matched × 2 + Nice_Matched × 1) / (Required_Total × 2 + Nice_Total × 1) × 100%
- Excluded skills do NOT affect the score
- Negative_Hit warning when resume has Excluded skills

Reference:
- Benchmarked against Jobscan for accuracy validation
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
from dify_plugin.entities.model.message import UserPromptMessage, SystemPromptMessage

# ============================================================================
# SYSTEM PROMPT - Core LLM Analysis Logic
# ============================================================================

SYSTEM_PROMPT_TEMPLATE = """You are an expert ATS (Applicant Tracking System) Analyzer. Your goal is to assess how well a candidate's resume matches a specific Job Description (JD).

### 1. KNOWN ALIASES (Synonyms)
Use these strict mappings for matching. If the resume uses an alias, count it as a match.
{synonym_map_str}

### 2. ANALYSIS LOGIC (Step-by-Step)

**Step 1: JD Extraction & Classification**
Extract technical skills/keywords from the JD and classify their importance:
- **Required**: Core skills, "must have", "proficient in", "X years of experience in"
- **Nice-to-have**: "Plus", "preferred", "bonus", "familiarity with"
- **Excluded**: Negative constraints like "No need for X", "Not X", "Unlike X", "We don't use X", "X is not required"

**Step 2: Evidence Verification**
For each skill found in JD, search the Resume for evidence:
- **Exact**: String appears exactly (case-insensitive). Example: JD "Python" → Resume "Python"
- **Substring**: Keyword exists inside a phrase. Example: JD "SQL" → Resume "MySQL" or "PostgreSQL"
- **Semantic**: Different words but same meaning. Example: JD "GPU Optimization" → Resume "TensorRT" (because TensorRT IS a GPU optimization tool)
- **Alias**: Known synonym from the alias list. Example: JD "Kubernetes" → Resume "k8s"

**Step 3: Frequency Count**
Count how many times the keyword appears in both JD and Resume.

### 3. OUTPUT SCHEMA (Strict JSON)
Return ONLY a valid JSON object. No markdown, no code blocks, no commentary.

{{
  "jd_analysis": {{
    "job_title": "String (extracted job title, or null if not found)",
    "skills_total": Integer
  }},
  "keyword_analysis": [
    {{
      "keyword": "String (normalized form, e.g., 'Kubernetes' not 'k8s')",
      "importance": "Required" | "Nice-to-have" | "Excluded",
      "match_status": "Matched" | "Missing",
      "match_type": "Exact" | "Substring" | "Semantic" | "Alias" | "None",
      "evidence": "String (max 50 chars quote from resume, or null if missing)",
      "reasoning": "String (ONLY for Semantic match, explain why they are related, else null)",
      "frequency": {{
        "jd": Integer,
        "resume": Integer
      }}
    }}
  ]
}}

### 4. IMPORTANT RULES
1. **Excluded + Matched**: If a skill is Excluded in JD but present in Resume, set match_status to "Matched". (Python logic will flag this as a warning)
2. **Excluded + Missing**: If a skill is Excluded in JD and NOT in Resume, set match_status to "Missing". (This is GOOD - user correctly lacks excluded skill)
3. **Focus on HARD SKILLS**: Do not extract generic terms like "Communication", "Teamwork", "Problem Solving" unless explicitly technical context.
4. **Alias Priority**: If resume uses an alias (e.g., "k8s"), normalize to standard form ("Kubernetes") in keyword field, set match_type to "Alias".
5. **Evidence Length**: Keep evidence under 50 characters. Truncate with "..." if needed.
6. **Reasoning**: ONLY provide reasoning for Semantic matches. For Exact/Substring/Alias, set reasoning to null.
"""


class KeywordMatcher(Tool):
    """
    ATS-Optimized Keyword Matcher with Semantic Analysis

    Features:
    - LLM-powered semantic matching (not just string matching)
    - Negative Constraint Recognition (Excluded skills)
    - Evidence-based matching (quotes from resume)
    - Weighted scoring (Required × 2, Nice-to-have × 1)
    - Graceful fallback to simple matching when LLM fails
    """

    # Complete synonym mapping (injected into LLM prompt)
    SYNONYM_MAP = {
        "k8s": "Kubernetes",
        "js": "JavaScript",
        "ts": "TypeScript",
        "py": "Python",
        "tf": "TensorFlow",
        "react.js": "React",
        "reactjs": "React",
        "vue.js": "Vue.js",
        "vuejs": "Vue.js",
        "node.js": "Node.js",
        "nodejs": "Node.js",
        "next.js": "Next.js",
        "nextjs": "Next.js",
        "express.js": "Express.js",
        "expressjs": "Express.js",
        "nest.js": "NestJS",
        "nestjs": "NestJS",
        "postgres": "PostgreSQL",
        "postgresql": "PostgreSQL",
        "mysql": "MySQL",
        "mongo": "MongoDB",
        "mongodb": "MongoDB",
        "aws": "Amazon Web Services",
        "gcp": "Google Cloud Platform",
        "azure": "Microsoft Azure",
        "ci/cd": "CI/CD",
        "cicd": "CI/CD",
        "ml": "Machine Learning",
        "dl": "Deep Learning",
        "ai": "Artificial Intelligence",
        "nlp": "Natural Language Processing",
        "cv": "Computer Vision",
        "golang": "Go",
        "cpp": "C++",
        "csharp": "C#",
        "dotnet": ".NET",
        "tf": "TensorFlow",
        "pt": "PyTorch",
        "pytorch": "PyTorch",
        "sklearn": "scikit-learn",
        "scikit-learn": "scikit-learn",
    }

    # Keywords that require case-sensitive matching (short names that could be common words)
    CASE_SENSITIVE_KEYWORDS = {"Go", "R", "C", "C++", "C#", ".NET"}

    # Fallback keywords when external dictionary is unavailable
    FALLBACK_KEYWORDS = [
        # Programming Languages
        "Python", "Java", "JavaScript", "TypeScript", "Go", "Rust", "C++", "C#", "Ruby", "PHP", "Swift", "Kotlin",
        # Frameworks
        "React", "Vue.js", "Angular", "Django", "Flask", "Spring Boot", "Node.js", "Express.js", "FastAPI",
        # Databases
        "MySQL", "PostgreSQL", "MongoDB", "Redis", "Elasticsearch", "SQLite", "Oracle", "SQL Server",
        # Cloud & DevOps
        "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "Jenkins", "GitHub Actions", "CI/CD",
        # AI/ML
        "Machine Learning", "Deep Learning", "TensorFlow", "PyTorch", "NLP", "Computer Vision", "LLM",
        # Data
        "Pandas", "NumPy", "Spark", "Hadoop", "ETL", "Data Pipeline", "SQL", "NoSQL",
        # Tools
        "Git", "Linux", "REST API", "GraphQL", "Microservices", "Agile", "Scrum",
    ]

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _generate_synonym_str(self) -> str:
        """Format SYNONYM_MAP for prompt injection."""
        return "\n".join([f"  - {k} → {v}" for k, v in self.SYNONYM_MAP.items()])

    def _clean_json_response(self, response_text: str) -> str:
        """Clean LLM response to extract valid JSON."""
        text = response_text.strip()
        # Remove markdown code blocks
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        # Find JSON object boundaries
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1:
            text = text[start:end+1]
        return text.strip()

    # ========================================================================
    # Main Entry Point
    # ========================================================================

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Main entry point for the KeywordMatcher tool.

        Flow:
        1. Validate inputs
        2. Try LLM semantic analysis
        3. If LLM fails, fallback to simple string matching
        4. Calculate weighted score
        5. Generate summary and return results
        """
        try:
            resume_text = tool_parameters.get('resume_text', '').strip()
            jd_text = tool_parameters.get('jd_text', '').strip()
            use_llm = tool_parameters.get('use_llm', True)

            # Validate inputs
            if not resume_text:
                yield self.create_text_message("[Error] Resume text cannot be empty")
                return

            if not jd_text:
                yield self.create_text_message(
                    "[Error] Job description (jd_text) is required.\n\n"
                    "For accurate ATS matching, please provide the complete job description text.\n"
                    "Auto-generated JDs may not reflect the specific requirements of your target position."
                )
                return

            # Get output format parameter
            output_format = tool_parameters.get('output_format', 'markdown')

            # Main analysis
            if use_llm:
                try:
                    result = self._analyze_with_llm(resume_text, jd_text)
                except Exception as e:
                    print(f"[Warning] LLM analysis failed: {e}, falling back to simple matching")
                    result = self._analyze_with_simple_matching(resume_text, jd_text)
                    result['warning'] = f"LLM 分析失败，已降级到基础匹配模式: {str(e)}"
            else:
                result = self._analyze_with_simple_matching(resume_text, jd_text)

            # Always output JSON message (for future Dify UI compatibility)
            yield self.create_json_message(result)

            # Conditional text output based on output_format
            if output_format == 'json':
                # Workflow mode: Output JSON string to bypass Dify UI type filtering
                # This allows ResumeOptimizer to receive the data as a String variable
                json_str = json.dumps(result, ensure_ascii=False, indent=2)
                yield self.create_text_message(json_str)
            else:
                # Chat mode (default): Output human-readable Markdown report
                summary = self._create_summary_v2(result)
                yield self.create_text_message(summary)

        except Exception as e:
            yield self.create_text_message(f"[Error] 关键词匹配失败: {str(e)}")

    # ========================================================================
    # Core Analysis Methods
    # ========================================================================

    def _analyze_with_llm(self, resume_text: str, jd_text: str) -> dict:
        """
        Perform semantic analysis using LLM.

        Steps:
        1. Construct prompt with SYNONYM_MAP context
        2. Call LLM with JD + Resume
        3. Parse JSON response
        4. Calculate weighted score
        5. Return structured result
        """
        # Build prompt
        synonyms_context = self._generate_synonym_str()
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(synonym_map_str=synonyms_context)

        user_content = f"""### JOB DESCRIPTION:
{jd_text}

### RESUME:
{resume_text}

Please analyze and output JSON."""

        # LLM configuration
        llm_config = {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "mode": "chat",
            "completion_params": {
                "temperature": 0.2,  # Low temperature for consistent JSON output
                "max_tokens": 4000
            }
        }

        # Retry logic
        max_retries = 3
        retry_delay = 1

        for attempt in range(max_retries):
            try:
                # Call LLM
                llm_result = self.session.model.llm.invoke(
                    model_config=LLMModelConfig(**llm_config),
                    prompt_messages=[
                        SystemPromptMessage(content=system_prompt),
                        UserPromptMessage(content=user_content)
                    ],
                    stream=False
                )

                response_text = llm_result.message.content.strip()

                if not response_text:
                    if attempt < max_retries - 1:
                        print(f"[Warning] LLM returned empty response (attempt {attempt + 1}/{max_retries})")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        raise ValueError("LLM returned empty response after all retries")

                # Clean and parse JSON
                clean_json = self._clean_json_response(response_text)
                llm_data = json.loads(clean_json)

                # Process result
                return self._process_llm_result(llm_data)

            except json.JSONDecodeError as e:
                if attempt < max_retries - 1:
                    print(f"[Warning] JSON parsing failed (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    raise ValueError(f"JSON parsing failed after all retries: {e}")

            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"[Warning] LLM call failed (attempt {attempt + 1}/{max_retries}): {e}")
                    time.sleep(retry_delay)
                    retry_delay *= 2
                    continue
                else:
                    raise

        raise ValueError("LLM analysis failed after all retries")

    def _process_llm_result(self, llm_data: dict) -> dict:
        """
        Process LLM JSON output and calculate weighted score.

        Score Formula:
        (Required_Matched × 2 + Nice_Matched × 1) / (Required_Total × 2 + Nice_Total × 1) × 100

        Excluded skills do NOT affect the score.
        """
        keywords = llm_data.get("keyword_analysis", [])
        jd_analysis = llm_data.get("jd_analysis", {})

        # Counters
        required_total = 0
        required_matched = 0
        nice_total = 0
        nice_matched = 0

        # Categorized results
        matched_keywords = []
        missing_keywords = []
        negative_hits = []  # Excluded but Matched (warning)
        compliant_excluded = []  # Excluded and Missing (good)

        for item in keywords:
            importance = item.get("importance", "Nice-to-have")
            status = item.get("match_status", "Missing")
            keyword = item.get("keyword", "")

            # Force normalize via SYNONYM_MAP (insurance layer)
            keyword = self.SYNONYM_MAP.get(keyword.lower(), keyword)

            # Build display item
            display_item = {
                "skill": keyword,
                "importance": importance,
                "match_type": item.get("match_type", "None"),
                "evidence": item.get("evidence"),
                "reasoning": item.get("reasoning"),
                "frequency": item.get("frequency", {"jd": 0, "resume": 0})
            }

            # Handle Excluded skills
            if importance == "Excluded":
                if status == "Matched":
                    # BAD: User has a skill that JD explicitly excludes
                    display_item["warning"] = "[Warning] JD 明确排除此技能，但简历中包含"
                    negative_hits.append(display_item)
                else:
                    # GOOD: User correctly lacks this excluded skill
                    display_item["status"] = "[OK] 合规"
                    compliant_excluded.append(display_item)
                continue  # Do NOT add to score calculation

            # Handle Required skills
            if importance == "Required":
                required_total += 1
                if status == "Matched":
                    required_matched += 1
                    matched_keywords.append(display_item)
                else:
                    display_item["priority"] = "高优先级"
                    missing_keywords.append(display_item)

            # Handle Nice-to-have skills
            elif importance == "Nice-to-have":
                nice_total += 1
                if status == "Matched":
                    nice_matched += 1
                    matched_keywords.append(display_item)
                else:
                    display_item["priority"] = "建议补充"
                    missing_keywords.append(display_item)

        # Calculate weighted score
        total_possible = (required_total * 2) + (nice_total * 1)
        earned_points = (required_matched * 2) + (nice_matched * 1)

        if total_possible > 0:
            match_rate = round((earned_points / total_possible) * 100, 1)
        else:
            match_rate = 0.0

        # Determine recommendation
        has_negative_hits = len(negative_hits) > 0

        if match_rate >= 80 and not has_negative_hits:
            status = "strongly_recommended"
            recommendation = "[PASS] 强烈推荐投递：简历高度匹配"
        elif match_rate >= 70 and not has_negative_hits:
            status = "recommended"
            recommendation = "[PASS] 推荐投递：简历匹配度良好"
        elif match_rate >= 60:
            status = "consider"
            recommendation = "[REVIEW] 可以考虑：建议优化后投递"
        else:
            status = "not_recommended"
            recommendation = "[FAIL] 不推荐投递：匹配度较低，建议优化"

        if has_negative_hits:
            recommendation += f"\n[Warning] 简历中包含 {len(negative_hits)} 个 JD 明确排除的技能"

        return {
            "match_analysis": {
                "match_rate": match_rate,
                "weighted_score": f"{earned_points}/{total_possible}",
                "status": status,
                "recommendation": recommendation,
                "required": {"matched": required_matched, "total": required_total},
                "nice_to_have": {"matched": nice_matched, "total": nice_total},
                "has_negative_constraints_violation": has_negative_hits
            },
            "match_details": {
                "matched": matched_keywords,
                "missing": missing_keywords,
                "negative_warnings": negative_hits,
                "excluded_compliant": compliant_excluded
            },
            "jd_analysis": jd_analysis,
            "source": "LLM_Semantic_Analysis"
        }

    def _analyze_with_simple_matching(self, resume_text: str, jd_text: str) -> dict:
        """
        Fallback: Simple string matching when LLM fails.

        Uses dictionary + synonym matching (legacy logic).
        Falls back to FALLBACK_KEYWORDS if external dictionary is unavailable.
        """
        # Try to load external dictionary, fall back to built-in keywords
        current_dir = Path(__file__).parent.parent
        dictionary_path = current_dir / "data" / "onet_keywords.json"
        keywords = self._load_dictionary(dictionary_path)

        # Use fallback if dictionary loading failed or returned empty
        if not keywords:
            keywords = self.FALLBACK_KEYWORDS

        # Extract keywords from both texts
        jd_keywords = self._extract_with_dictionary(jd_text, keywords)
        resume_keywords_set = set()

        # Build resume keywords set
        for kw in self._extract_with_dictionary(resume_text, keywords):
            resume_keywords_set.add(kw['skill'].lower())

        # Match
        matched = []
        missing = []

        for jd_kw in jd_keywords:
            skill = jd_kw['skill']
            count, match_type = self._count_mentions(skill, resume_text)

            if count > 0:
                matched.append({
                    "skill": skill,
                    "importance": "Nice-to-have",  # Cannot determine without LLM
                    "match_type": "Exact" if match_type == "exact" else "Alias",
                    "evidence": None,
                    "reasoning": None,
                    "frequency": {"jd": jd_kw.get('mentions', 1), "resume": count}
                })
            else:
                missing.append({
                    "skill": skill,
                    "importance": "Nice-to-have",
                    "match_type": "None",
                    "evidence": None,
                    "reasoning": None,
                    "frequency": {"jd": jd_kw.get('mentions', 1), "resume": 0},
                    "priority": "建议补充"
                })

        # Simple score (no weighting in fallback mode)
        total = len(jd_keywords)
        matched_count = len(matched)
        match_rate = round((matched_count / total * 100) if total > 0 else 0, 1)

        if match_rate >= 70:
            status = "recommended"
            recommendation = "[PASS] 推荐投递（基础匹配模式）"
        elif match_rate >= 50:
            status = "consider"
            recommendation = "[REVIEW] 可以考虑（基础匹配模式）"
        else:
            status = "not_recommended"
            recommendation = "[FAIL] 建议优化后投递（基础匹配模式）"

        return {
            "match_analysis": {
                "match_rate": match_rate,
                "weighted_score": f"{matched_count}/{total}",
                "status": status,
                "recommendation": recommendation,
                "required": {"matched": 0, "total": 0},
                "nice_to_have": {"matched": matched_count, "total": total},
                "has_negative_constraints_violation": False
            },
            "match_details": {
                "matched": matched,
                "missing": missing,
                "negative_warnings": [],
                "excluded_compliant": []
            },
            "jd_analysis": {"job_title": None, "skills_total": total},
            "source": "Fallback_Simple_Match"
        }

    def _create_summary_v2(self, result: dict) -> str:
        """Create human-readable summary for v2 (semantic analysis)."""
        analysis = result.get("match_analysis", {})
        details = result.get("match_details", {})

        match_rate = analysis.get("match_rate", 0)
        source = result.get("source", "Unknown")

        # Status indicator based on score
        if match_rate >= 80:
            indicator = "[PASS]"
        elif match_rate >= 70:
            indicator = "[GOOD]"
        elif match_rate >= 60:
            indicator = "[REVIEW]"
        else:
            indicator = "[FAIL]"

        lines = [
            "# ATS Semantic Analysis Report",
            "",
            f"## {indicator} Match Rate: {match_rate}%",
            "",
            analysis.get("recommendation", ""),
            "",
            "---",
            "",
            "## Match Details",
            "",
            f"- **Required Skills**: {analysis.get('required', {}).get('matched', 0)}/{analysis.get('required', {}).get('total', 0)} matched",
            f"- **Nice-to-have Skills**: {analysis.get('nice_to_have', {}).get('matched', 0)}/{analysis.get('nice_to_have', {}).get('total', 0)} matched",
            f"- **Weighted Score**: {analysis.get('weighted_score', 'N/A')}",
            "",
        ]

        # Negative warnings
        negative_warnings = details.get("negative_warnings", [])
        if negative_warnings:
            lines.extend([
                "## [Warning] Negative Constraint Violations",
                "",
                "The following skills are explicitly NOT wanted by JD, but found in your resume:",
                "",
            ])
            for item in negative_warnings:
                lines.append(f"- **{item['skill']}**: {item.get('evidence', 'Found in resume')}")
            lines.append("")

        # Matched keywords
        matched = details.get("matched", [])
        if matched:
            lines.extend([
                "## [OK] Matched Keywords",
                "",
            ])
            for item in matched[:10]:
                match_type = item.get("match_type", "")
                evidence = item.get("evidence", "")
                if evidence:
                    lines.append(f"- **{item['skill']}** ({match_type}): \"{evidence}\"")
                else:
                    lines.append(f"- **{item['skill']}** ({match_type})")
            if len(matched) > 10:
                lines.append(f"  ...and {len(matched) - 10} more")
            lines.append("")

        # Missing keywords
        missing = details.get("missing", [])
        if missing:
            lines.extend([
                "## [Missing] Keywords Not Found",
                "",
            ])
            # Separate by priority
            required_missing = [m for m in missing if m.get("importance") == "Required"]
            nice_missing = [m for m in missing if m.get("importance") == "Nice-to-have"]

            if required_missing:
                lines.append("### Required Skills (High Priority)")
                for item in required_missing[:5]:
                    lines.append(f"- **{item['skill']}**")
                if len(required_missing) > 5:
                    lines.append(f"  ...and {len(required_missing) - 5} more")
                lines.append("")

            if nice_missing:
                lines.append("### Nice-to-have Skills (Recommended)")
                for item in nice_missing[:5]:
                    lines.append(f"- {item['skill']}")
                if len(nice_missing) > 5:
                    lines.append(f"  ...and {len(nice_missing) - 5} more")
                lines.append("")

        # Footer
        lines.extend([
            "---",
            "",
            "## Notes",
            "",
            f"- **Analysis Mode**: {source}",
            "- **Scoring Formula**: (Required x 2 + Nice-to-have x 1) / Total x 100%",
            "- **Match Types**: Exact | Substring | Semantic | Alias",
        ])

        return "\n".join(lines)

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

        # 2. Synonym match (using SYNONYM_MAP)
        # Build reverse mapping: standard form -> list of aliases
        reverse_synonyms = {}
        for alias, standard in self.SYNONYM_MAP.items():
            if standard not in reverse_synonyms:
                reverse_synonyms[standard] = []
            reverse_synonyms[standard].append(alias)

        synonyms = reverse_synonyms.get(keyword, [])
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

    # ========================================================================
    # Legacy methods removed in v0.5.0:
    # - _extract_with_llm (replaced by _analyze_with_llm)
    # - _merge_keywords (no longer needed)
    # - _extract_keywords_dual_engine (no longer needed)
    # - _calculate_match_score (replaced by _process_llm_result)
    # - _generate_simple_optimization_suggestions (no longer needed)
    # - _create_summary (replaced by _create_summary_v2)
    # - _parse_resume_keywords_input (no longer needed - resume_keywords param removed)
    # - _generate_standard_jd_requirements (removed - require user to provide JD)
    # - _extract_keywords_from_generated_jd (removed - no longer needed)
    # ========================================================================

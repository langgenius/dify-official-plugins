"""
Keyword Extraction Tool for Dingo - Dual-Engine Hybrid Architecture

Combines dictionary-based regex matching (millisecond response) with LLM semantic analysis
(deep reasoning) to extract technology keywords from resume text.

Architecture:
1. Dictionary Engine: Fast regex matching using O*NET keywords (221 keywords, 13 categories)
2. LLM Engine: Semantic analysis to infer implicit skills from project descriptions
3. Synonym Normalization: K8s→Kubernetes, JS→JavaScript, etc.
4. Confidence Weighting: Dictionary=1.0, LLM=0.7-0.9
5. Result Merging: Deduplicate and merge results from both engines

Reference: Resume-Matcher/apps/backend/app/services/score_improvement_service.py
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


# Technology Synonyms Dictionary (Standard Term → Synonyms List)
# Used for bidirectional matching: JD keyword → Resume variations
# This is defined at module level so it can be imported by other tools
TECH_SYNONYMS = {
    # Programming Languages
    "Python": ["python", "Python3", "Python2", "py", "Python编程"],
    "JavaScript": ["javascript", "js", "JS", "ECMAScript"],
    "TypeScript": ["typescript", "ts", "TS"],
    "Java": ["java", "JAVA"],
    "Go": ["golang", "Golang"],
    "C++": ["c++", "cpp", "CPP"],
    "C#": ["c#", "csharp", "C Sharp"],
    "R": ["r语言"],
    "PHP": ["php"],
    "Ruby": ["ruby"],
    "Swift": ["swift"],
    "Kotlin": ["kotlin"],
    "Rust": ["rust"],
    "Scala": ["scala"],

    # Frontend Frameworks
    "React": ["react", "react.js", "ReactJS", "React.js"],
    "Vue.js": ["vue", "vuejs", "Vue", "vue.js"],
    "Angular": ["angular", "angularjs", "AngularJS"],
    "Next.js": ["nextjs", "next", "next.js"],
    "Nuxt.js": ["nuxtjs", "nuxt", "nuxt.js"],

    # Backend Frameworks
    "Django": ["django"],
    "Flask": ["flask"],
    "FastAPI": ["fastapi", "fast api"],
    "Spring": ["spring", "spring boot", "springboot", "Spring Boot"],
    "Express.js": ["express", "expressjs", "express.js"],
    "NestJS": ["nestjs", "nest.js", "nest"],
    "Laravel": ["laravel"],
    "Ruby on Rails": ["rails", "ruby on rails", "RoR"],

    # Machine Learning / AI Frameworks
    "TensorFlow": ["tensorflow", "tf", "TF", "Tensorflow"],
    "PyTorch": ["pytorch", "torch", "Pytorch"],
    "Keras": ["keras"],
    "Scikit-learn": ["scikit-learn", "sklearn", "scikit learn"],
    "XGBoost": ["xgboost", "xgb"],
    "LightGBM": ["lightgbm", "lgbm"],
    "Hugging Face": ["huggingface", "hugging face", "transformers"],

    # Databases
    "PostgreSQL": ["postgresql", "postgres", "pg", "Postgres"],
    "MySQL": ["mysql", "My SQL"],
    "MongoDB": ["mongodb", "mongo", "Mongo"],
    "Redis": ["redis"],
    "Elasticsearch": ["elasticsearch", "elastic search", "ES", "ElasticSearch"],
    "Oracle": ["oracle"],
    "SQL Server": ["sql server", "mssql", "MS SQL"],
    "SQLite": ["sqlite"],
    "Cassandra": ["cassandra"],
    "DynamoDB": ["dynamodb", "dynamo db"],

    # Cloud Services
    "AWS": ["aws", "Amazon Web Services", "亚马逊云"],
    "GCP": ["gcp", "Google Cloud", "谷歌云", "Google Cloud Platform"],
    "Azure": ["azure", "微软云", "Microsoft Azure"],
    "Alibaba Cloud": ["阿里云", "aliyun", "alibaba cloud"],
    "Tencent Cloud": ["腾讯云", "tencent cloud"],

    # DevOps / Infrastructure
    "Docker": ["docker", "容器化", "containerization"],
    "Kubernetes": ["kubernetes", "k8s", "K8s", "K8S", "容器编排"],
    "CI/CD": ["ci/cd", "cicd", "持续集成", "持续部署", "CI CD"],
    "Jenkins": ["jenkins"],
    "GitLab CI": ["gitlab ci", "gitlab-ci", "GitLab CI/CD"],
    "GitHub Actions": ["github actions", "github action"],
    "Terraform": ["terraform"],
    "Ansible": ["ansible"],
    "Prometheus": ["prometheus"],
    "Grafana": ["grafana"],
    "Nginx": ["nginx"],
    "Apache": ["apache"],

    # Machine Learning / AI Concepts
    "Machine Learning": ["machine learning", "ml", "ML", "机器学习"],
    "Deep Learning": ["deep learning", "dl", "DL", "深度学习", "神经网络"],
    "Natural Language Processing": ["nlp", "NLP", "自然语言处理", "文本处理"],
    "Computer Vision": ["cv", "CV", "计算机视觉", "图像处理"],
    "Artificial Intelligence": ["ai", "AI", "人工智能"],
    "Reinforcement Learning": ["reinforcement learning", "rl", "RL", "强化学习"],
    "Transfer Learning": ["transfer learning", "迁移学习"],
    "Large Language Model": ["llm", "LLM", "大语言模型", "大模型"],

    # Methodologies
    "Agile": ["agile", "敏捷开发", "敏捷"],
    "Scrum": ["scrum"],
    "DevOps": ["devops", "dev ops"],
    "Microservices": ["microservices", "微服务", "micro services"],
    "RESTful API": ["restful", "rest api", "RESTful", "REST"],
    "GraphQL": ["graphql"],
    "Test-Driven Development": ["tdd", "TDD", "test-driven development", "测试驱动开发"],

    # Tools
    "Git": ["git"],
    "GitHub": ["github"],
    "GitLab": ["gitlab"],
    "Bitbucket": ["bitbucket"],
    "Jira": ["jira"],
    "Confluence": ["confluence"],
    "Slack": ["slack"],
    "VS Code": ["vscode", "vs code", "visual studio code"],
    "PyCharm": ["pycharm"],
    "IntelliJ IDEA": ["intellij", "intellij idea", "idea"],

    # Data Science / Big Data
    "Pandas": ["pandas"],
    "NumPy": ["numpy"],
    "Matplotlib": ["matplotlib"],
    "Seaborn": ["seaborn"],
    "Jupyter": ["jupyter", "jupyter notebook"],
    "Apache Spark": ["spark", "apache spark", "pyspark"],
    "Hadoop": ["hadoop"],
    "Kafka": ["kafka", "apache kafka"],
    "Airflow": ["airflow", "apache airflow"],

    # Mobile Development
    "React Native": ["react native", "react-native", "reactnative"],
    "Flutter": ["flutter"],
    "iOS": ["ios"],
    "Android": ["android"],
    "SwiftUI": ["swiftui", "swift ui"],

    # Other
    "Linux": ["linux"],
    "Unix": ["unix"],
    "Shell": ["shell", "bash", "zsh"],
    "SQL": ["sql"],
    "NoSQL": ["nosql", "no sql"],
    "API": ["api"],
    "Blockchain": ["blockchain", "区块链"],
    "Cryptocurrency": ["cryptocurrency", "crypto", "加密货币"],
}


class KeywordExtraction(Tool):
    """
    Dual-Engine Keyword Extractor: Dictionary Matching + LLM Semantic Analysis

    Engine 1 (Dictionary): Fast regex matching using O*NET keywords
    Engine 2 (LLM): Semantic analysis to infer implicit skills

    This implementation combines Resume-Matcher's battle-tested regex logic
    with LLM-powered deep reasoning for comprehensive keyword extraction.
    """

    # Keywords that need case-sensitive matching to avoid false positives
    CASE_SENSITIVE_KEYWORDS = {"Go", "R"}

    # Synonym mapping for normalization (K8s→Kubernetes, etc.)
    # This is used for backward compatibility with existing code
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

    # LLM Prompt for semantic keyword extraction
    LLM_PROMPT_TEMPLATE = """You are a technical keyword extraction expert. Analyze the following resume text and extract ALL technology-related keywords.

**Your Task:**
1. Extract explicit keywords (directly mentioned technologies)
2. Infer implicit keywords from project descriptions (e.g., "built microservices" → Docker, Kubernetes)
3. Identify soft skills from leadership/teamwork descriptions
4. Normalize synonyms (K8s→Kubernetes, JS→JavaScript)

**Categories to Extract:**
- Programming Languages (Python, Java, JavaScript, etc.)
- Frameworks (React, Django, Spring, etc.)
- Databases (PostgreSQL, MongoDB, Redis, etc.)
- Cloud/DevOps (AWS, Docker, Kubernetes, CI/CD, etc.)
- Tools (Git, GitHub, Jenkins, etc.)
- Methodologies (Agile, Scrum, TDD, etc.)
- Soft Skills (Leadership, Communication, Problem Solving, etc.)

**Output Format (JSON only, no markdown):**
{{
  "keywords": [
    {{"skill": "Python", "confidence": 1.0, "source": "explicit", "context": "mentioned in skills section"}},
    {{"skill": "Docker", "confidence": 0.85, "source": "inferred", "context": "inferred from 'containerized applications'"}},
    {{"skill": "Leadership", "confidence": 0.8, "source": "inferred", "context": "inferred from 'led a team of 5'"}}
  ]
}}

**Confidence Scoring:**
- 1.0: Explicitly mentioned (exact match)
- 0.8-0.9: Strong inference (clear context)
- 0.7: Weak inference (possible but uncertain)

**Resume Text:**
```
{resume_text}
```

**Important:** Output ONLY valid JSON. No markdown, no explanations."""

    @staticmethod
    def _load_dictionary(dictionary_path: Path) -> list[str]:
        """Load and flatten the keyword dictionary."""
        with open(dictionary_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Flatten all categories into a single list
        all_keywords = []
        for category, keywords in data.get("keywords", {}).items():
            all_keywords.extend(keywords)

        return all_keywords

    @staticmethod
    def _clean_json_response(response_text: str) -> str:
        """Clean up LLM response to extract valid JSON."""
        # Remove markdown code blocks
        if response_text.startswith("```json"):
            response_text = response_text[7:]
        if response_text.startswith("```"):
            response_text = response_text[3:]
        if response_text.endswith("```"):
            response_text = response_text[:-3]

        # Remove any leading/trailing whitespace
        response_text = response_text.strip()

        # Try to find JSON object boundaries
        start_idx = response_text.find('{')
        if start_idx > 0:
            response_text = response_text[start_idx:]

        return response_text

    @staticmethod
    def _repair_truncated_json(json_str: str) -> str | None:
        """
        Attempt to repair truncated JSON by closing open brackets.

        Returns repaired JSON string or None if repair failed.
        """
        try:
            # Count open brackets
            open_braces = json_str.count('{') - json_str.count('}')
            open_brackets = json_str.count('[') - json_str.count(']')

            # If severely unbalanced, try to find last complete entry
            if open_braces > 2 or open_brackets > 2:
                # Find the last complete keyword entry (ends with })
                last_complete = json_str.rfind('},')
                if last_complete > 0:
                    json_str = json_str[:last_complete + 1]
                    # Recount after truncation
                    open_braces = json_str.count('{') - json_str.count('}')
                    open_brackets = json_str.count('[') - json_str.count(']')

            # Remove trailing comma if present
            json_str = json_str.rstrip().rstrip(',')

            # Close brackets
            json_str += ']' * open_brackets
            json_str += '}' * open_braces

            # Validate by parsing
            json.loads(json_str)
            return json_str
        except Exception:
            return None

    @staticmethod
    def _prepare_text_for_matching(text: str) -> str:
        """
        Prepare text for keyword matching by normalizing format.
        
        Directly adapted from Resume-Matcher's _prepare_text_for_matching().
        
        Steps:
        1. Convert to lowercase
        2. Remove Markdown symbols: ` * _ > - (but preserve # for C#, F#)
        3. Collapse multiple whitespaces into single space
        
        Args:
            text: Raw resume text (may contain Markdown)
        
        Returns:
            Normalized text ready for regex matching
        """
        lowered = text.lower()
        # Remove Markdown symbols (but preserve # for C#, F#)
        lowered = re.sub(r"[`*_>\-]", " ", lowered)
        # Remove standalone # (Markdown headers) but keep c#, f#
        lowered = re.sub(r"(?<![a-z])#(?![a-z])", " ", lowered)
        # Collapse multiple whitespaces
        lowered = re.sub(r"\s+", " ", lowered)
        return lowered
    
    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Main entry point for Dify tool invocation.

        Args:
            tool_parameters: Tool parameters from Dify

        Yields:
            ToolInvokeMessage: JSON and text messages
        """
        try:
            # Extract parameters
            resume_text = tool_parameters.get('resume_text', '').strip()
            use_llm = tool_parameters.get('use_llm', True)

            if not resume_text:
                yield self.create_text_message("❌ Resume text cannot be empty")
                return

            # Load keyword dictionary
            current_dir = Path(__file__).parent.parent
            dictionary_path = current_dir / "data" / "onet_keywords.json"
            keywords = self._load_dictionary(dictionary_path)

            # Run dual-engine extraction
            result = self._extract_keywords_dual_engine(resume_text, use_llm, keywords)

            # Create summary text
            summary = self._create_summary(result)

            # Yield results (using the same pattern as resume_quality_checker)
            json_message = self.create_json_message(result)
            text_message = self.create_text_message(summary)
            yield from [json_message, text_message]

        except Exception as e:
            yield self.create_text_message(f"❌ Extraction failed: {str(e)}")

    def _extract_keywords_dual_engine(self, resume_text: str, use_llm: bool, keywords: list[str]) -> dict[str, Any]:
        """
        Dual-Engine Keyword Extraction: Dictionary + LLM

        Engine 1: Dictionary-based regex matching (fast, precise)
        Engine 2: LLM semantic analysis (deep, inferred)

        Args:
            resume_text: Raw resume text
            use_llm: Whether to use LLM engine
            keywords: List of keywords from dictionary

        Returns:
            Merged results from both engines with confidence weighting
        """
        # Engine 1: Dictionary-based extraction (always run)
        dict_results = self._extract_with_dictionary(resume_text, keywords)

        # Engine 2: LLM-based extraction (optional)
        llm_results = []
        if use_llm:
            llm_results = self._extract_with_llm(resume_text)

        # Merge results with confidence weighting
        merged_keywords = self._merge_results(dict_results, llm_results)

        return {
            "keywords": merged_keywords,
            "total_keywords": len(merged_keywords),
            "dictionary_version": "1.0.0",
            "engines_used": ["dictionary", "llm"] if use_llm else ["dictionary"],
            "dictionary_matches": len(dict_results),
            "llm_inferences": len(llm_results)
        }

    def _extract_with_dictionary(self, resume_text: str, keywords: list[str]) -> list[dict[str, Any]]:
        """
        Engine 1: Dictionary-based regex matching (millisecond response)

        Directly adapted from Resume-Matcher's _build_skill_comparison().

        Args:
            resume_text: Raw resume text
            keywords: List of keywords from dictionary
        """
        if not keywords:
            return []

        # Normalize synonyms first
        resume_normalized = self._normalize_synonyms(resume_text)
        resume_norm = self._prepare_text_for_matching(resume_normalized)

        results = []

        for keyword in keywords:
            # Use case-sensitive matching for special keywords (Go, R)
            if keyword in self.CASE_SENSITIVE_KEYWORDS:
                pattern = re.compile(rf"(?<!\w){re.escape(keyword)}(?!\w)")
                mentions = len(pattern.findall(resume_normalized))
            else:
                kw_lower = keyword.lower()
                # Word boundary regex: (?<!\w)keyword(?!\w)
                pattern = re.compile(rf"(?<!\w){re.escape(kw_lower)}(?!\w)")
                mentions = len(pattern.findall(resume_norm))

            if mentions > 0:
                results.append({
                    "skill": keyword,
                    "mentions": mentions,
                    "confidence": 1.0,  # Dictionary match = 100% confidence
                    "source": "dictionary",
                    "context": "explicit mention"
                })

        return results

    def _extract_with_llm(self, resume_text: str) -> list[dict[str, Any]]:
        """
        Engine 2: LLM semantic analysis (deep reasoning)

        Uses LLM to infer implicit skills from project descriptions.
        """
        try:
            # Build prompt
            prompt = self.LLM_PROMPT_TEMPLATE.format(resume_text=resume_text)
            prompt_messages = [UserPromptMessage(content=prompt)]

            # LLM configuration (using DeepSeek)
            llm_config = {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "mode": "chat",
                "completion_params": {
                    "temperature": 0.3,  # Lower temperature for more precise extraction
                    "max_tokens": 4000  # Increased to avoid truncation
                }
            }

            # Retry logic for LLM invocation
            max_retries = 3
            retry_delay = 1  # Initial delay in seconds

            for attempt in range(max_retries):
                try:
                    # Invoke LLM
                    llm_result = self.session.model.llm.invoke(
                        model_config=LLMModelConfig(**llm_config),
                        prompt_messages=prompt_messages,
                        stream=False
                    )

                    # Parse LLM response
                    if llm_result and hasattr(llm_result, 'message') and hasattr(llm_result.message, 'content'):
                        response_text = llm_result.message.content.strip()

                        # Check for empty response
                        if not response_text:
                            if attempt < max_retries - 1:
                                print(f"⚠️ LLM returned empty response (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                                time.sleep(retry_delay)
                                retry_delay *= 2  # Exponential backoff
                                continue
                            else:
                                print(f"❌ LLM returned empty response after {max_retries} attempts")
                                return []

                        # Clean up response text
                        response_text = self._clean_json_response(response_text)

                        # Parse JSON with repair attempt
                        try:
                            llm_data = json.loads(response_text)
                        except json.JSONDecodeError:
                            # Try to repair truncated JSON
                            repaired = self._repair_truncated_json(response_text)
                            if repaired:
                                llm_data = json.loads(repaired)
                            else:
                                raise

                        keywords = llm_data.get("keywords", [])

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

                    # No valid response
                    if attempt < max_retries - 1:
                        print(f"⚠️ LLM returned invalid response (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
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

        except Exception as e:
            # LLM failure is non-fatal, fall back to dictionary-only
            return []

    def _normalize_synonyms(self, text: str) -> str:
        """
        Normalize synonyms in text (K8s→Kubernetes, JS→JavaScript, etc.)
        """
        normalized = text
        for synonym, standard in self.SYNONYM_MAP.items():
            # Case-insensitive replacement with word boundaries
            pattern = re.compile(rf"(?<!\w){re.escape(synonym)}(?!\w)", re.IGNORECASE)
            normalized = pattern.sub(standard, normalized)
        return normalized

    def _merge_results(self, dict_results: list[dict], llm_results: list[dict]) -> list[dict]:
        """
        Merge dictionary and LLM results with deduplication and confidence weighting.

        Strategy:
        1. Dictionary results have priority (confidence=1.0)
        2. LLM results are added if not already in dictionary results
        3. If same skill appears in both, use dictionary result (higher confidence)
        """
        # Create a map of skills from dictionary results
        skill_map = {}
        for item in dict_results:
            skill = item["skill"]
            skill_map[skill.lower()] = item

        # Add LLM results if not already present
        for item in llm_results:
            skill = item.get("skill", "")
            skill_lower = skill.lower()

            if skill_lower not in skill_map:
                # New skill from LLM
                skill_map[skill_lower] = {
                    "skill": skill,
                    "mentions": 0,  # LLM doesn't count mentions
                    "confidence": item.get("confidence", 0.8),
                    "source": item.get("source", "llm"),
                    "context": item.get("context", "inferred by LLM")
                }
            # If skill already in dictionary, skip LLM result (dictionary has priority)

        # Convert back to list and sort by confidence (desc) then mentions (desc)
        merged = list(skill_map.values())
        merged.sort(key=lambda x: (x["confidence"], x.get("mentions", 0)), reverse=True)

        return merged

    def _create_summary(self, result: dict[str, Any]) -> str:
        """
        Create a human-readable summary of extraction results.
        """
        keywords = result.get("keywords", [])
        total = result.get("total_keywords", 0)
        engines = result.get("engines_used", [])
        dict_count = result.get("dictionary_matches", 0)
        llm_count = result.get("llm_inferences", 0)

        # Build summary
        lines = [
            "# 🎯 Keyword Extraction Results",
            "",
            f"**Total Keywords Extracted:** {total}",
            f"**Engines Used:** {', '.join(engines).upper()}",
            f"**Dictionary Matches:** {dict_count}",
            f"**LLM Inferences:** {llm_count}",
            "",
            "## 📊 Extracted Keywords",
            ""
        ]

        # Group by confidence
        high_conf = [kw for kw in keywords if kw["confidence"] >= 0.9]
        medium_conf = [kw for kw in keywords if 0.7 <= kw["confidence"] < 0.9]
        low_conf = [kw for kw in keywords if kw["confidence"] < 0.7]

        if high_conf:
            lines.append(f"### ✅ High Confidence ({len(high_conf)} keywords)")
            for kw in high_conf[:20]:  # Show top 20
                mentions_str = f" ({kw['mentions']} mentions)" if kw.get('mentions', 0) > 0 else ""
                lines.append(f"- **{kw['skill']}**{mentions_str} - {kw.get('context', 'N/A')}")
            if len(high_conf) > 20:
                lines.append(f"- ... and {len(high_conf) - 20} more")
            lines.append("")

        if medium_conf:
            lines.append(f"### ⚠️ Medium Confidence ({len(medium_conf)} keywords)")
            for kw in medium_conf[:10]:  # Show top 10
                lines.append(f"- **{kw['skill']}** (confidence: {kw['confidence']:.2f}) - {kw.get('context', 'N/A')}")
            if len(medium_conf) > 10:
                lines.append(f"- ... and {len(medium_conf) - 10} more")
            lines.append("")

        if low_conf:
            lines.append(f"### ℹ️ Low Confidence ({len(low_conf)} keywords)")
            lines.append("(These are weak inferences and may not be accurate)")
            lines.append("")

        return "\n".join(lines)


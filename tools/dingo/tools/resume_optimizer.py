from typing import Any
from collections.abc import Generator
import time

from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.entities.model.llm import LLMModelConfig
from dify_plugin.entities.model.message import UserPromptMessage


class ResumeOptimizerTool(Tool):
    """
    Resume optimization tool with bilingual support and target position integration.

    This tool helps users optimize their resumes for specific job positions using LLM.
    It supports both file upload and text input, with bilingual prompts.
    """

    PROMPTS = {
        "zh_Hans": """你是一位资深的简历优化专家。请针对【{target_position}】岗位，直接给出具体的修改建议。

目标岗位：{target_position}

{detected_issues_section}

## 重要约束

简历内容可能是从 PDF/DOCX 转换为 Markdown 的，可能存在格式转换问题。

**请只关注简历的实质内容优化**：
- 关键词匹配度（是否包含岗位要求的核心技术栈和技能）
- 工作经历和项目经验的描述（是否突出相关经验）
- 技能展示和量化成果（是否用数据说话）
- 内容的专业性和针对性（是否符合岗位要求）

**请忽略以下问题，不要在优化建议中提及**：
- Markdown 格式问题（多余空格、换行、符号丢失、缩进等）
- 排版和布局问题
- 文件格式问题

这些格式问题可能是转换工具导致的，在原始文件中不存在。用户会在原始文件中应用你的内容优化建议。

## 输出要求

**不要**自我介绍、不要分析问题、不要介绍工作计划，**直接开始输出优化建议**。

按照简历的实际模块结构（如：教育背景、工作经历、项目经验、专业技能等），逐一给出优化建议。

每条建议必须包含：
- **改前**：从简历中摘录需要修改的原文（保持原文格式）
- **改后**：优化后的表述（可直接复制粘贴使用）
- **优化理由**：1-2 句话说明为什么这样改更适合【{target_position}】岗位

## 输出格式

### 📋 [模块名称]

**改前**：
```
[从简历中摘录的原文]
```

**改后**：
```
[优化后的表述]
```

**优化理由**：[简洁说明]

---

### 📋 [下一个模块名称]

**改前**：
```
[原文]
```

**改后**：
```
[优化后的表述]
```

**优化理由**：[简洁说明]

---

{issues_fix_section}

## 优化重点

1. **关键词匹配**：确保简历包含【{target_position}】岗位的核心技术栈和关键词
2. **量化成果**：用数据说话（如：性能提升 X%、处理量 X 万次/日）
3. **动作动词**：使用"设计、实现、优化、负责"等强动作词，避免"参与、了解"
4. **岗位相关性**：突出与目标岗位最相关的经验，弱化无关内容
5. **STAR 法则**：Situation（背景）→ Task（任务）→ Action（行动）→ Result（结果）

## 注意事项

- 只针对**需要优化的内容**给出建议，已经很好的部分可以跳过
- 每条建议都要**具体、可操作**，用户可以直接复制粘贴
- 保持简历的**原有结构和风格**，不要大幅改变排版
- 如果简历中某些模块缺失但对目标岗位重要，可以建议添加

---

**现在开始输出优化建议**（不要任何开场白，直接从第一个模块开始）：

简历内容：
{resume_content}""",

        "en_US": """You are a seasoned resume optimization expert. Please provide specific modification suggestions for the [{target_position}] position.

Target Position: {target_position}

{detected_issues_section}

## Important Constraints

The resume content may have been converted from PDF/DOCX to Markdown, which may introduce format conversion issues.

**Please focus ONLY on substantive content optimization**:
- Keyword matching (does it include core tech stack and skills required for the position)
- Work experience and project descriptions (does it highlight relevant experience)
- Skills showcase and quantified achievements (does it use data to demonstrate impact)
- Content professionalism and relevance (does it align with position requirements)

**Please IGNORE the following issues and do NOT mention them in your suggestions**:
- Markdown formatting issues (extra spaces, line breaks, missing symbols, indentation, etc.)
- Layout and formatting problems
- File format issues

These formatting issues may be caused by conversion tools and do not exist in the original file. Users will apply your content optimization suggestions to their original files.

## Output Requirements

**Do NOT** introduce yourself, analyze problems, or describe your work plan. **Start directly with optimization suggestions**.

Provide suggestions for each actual section in the resume (e.g., Education, Work Experience, Projects, Skills, etc.).

Each suggestion must include:
- **Before**: Original text from the resume (keep original format)
- **After**: Optimized version (ready to copy-paste)
- **Reason**: 1-2 sentences explaining why this change better fits the [{target_position}] position

## Output Format

### 📋 [Section Name]

**Before**:
```
[Original text from resume]
```

**After**:
```
[Optimized version]
```

**Reason**: [Brief explanation]

---

### 📋 [Next Section Name]

**Before**:
```
[Original text]
```

**After**:
```
[Optimized version]
```

**Reason**: [Brief explanation]

---

{issues_fix_section}

## Optimization Focus

1. **Keyword Matching**: Ensure resume includes core tech stack and keywords for [{target_position}]
2. **Quantified Achievements**: Use data (e.g., improved performance by X%, handled X requests/day)
3. **Action Verbs**: Use strong verbs like "designed, implemented, optimized, led" instead of "participated, familiar with"
4. **Job Relevance**: Highlight most relevant experience for target position, de-emphasize irrelevant content
5. **STAR Method**: Situation → Task → Action → Result

## Guidelines

- Only provide suggestions for **content that needs improvement**; skip parts that are already good
- Each suggestion should be **specific and actionable**, ready to copy-paste
- Maintain the **original structure and style** of the resume, don't drastically change layout
- If important sections are missing for the target position, suggest adding them

---

**Start outputting optimization suggestions now** (no introduction, start directly from the first section):

Resume Content:
{resume_content}"""
    }

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Invoke the resume optimizer tool.

        Args:
            tool_parameters: Tool parameters including resume_content, target_position, detected_issues, and language

        Returns:
            Generator of ToolInvokeMessage
        """
        try:
            # Extract and validate parameters
            target_position = tool_parameters.get('target_position', '').strip()
            detected_issues = tool_parameters.get('detected_issues', '').strip()
            language = tool_parameters.get('language', 'zh_Hans')

            # Get resume content from file upload or text input
            resume_content, error_msg = self._get_resume_content(tool_parameters, language)
            if error_msg:
                yield self.create_text_message(error_msg)
                return

            # Validate required parameters
            if not target_position:
                error_msg = "目标岗位不能为空" if language == 'zh_Hans' else "Target position cannot be empty"
                yield self.create_text_message(error_msg)
                return

            # Generate optimization suggestions using LLM
            result = self._optimize_resume_with_llm(resume_content, target_position, detected_issues, language)
            yield self.create_text_message(result)

        except Exception as e:
            error_msg = f"优化过程中出现错误: {str(e)}" if language == 'zh_Hans' else f"Error during optimization: {str(e)}"
            yield self.create_text_message(error_msg)

    def _get_resume_content(self, tool_parameters: dict[str, Any], language: str) -> tuple[str, str]:
        """
        Extract resume content from text input.

        Returns:
            tuple: (resume_content, error_message)
        """
        # Get resume content from text input
        resume_content = tool_parameters.get('resume_content', '').strip()
        if not resume_content:
            error_msg = "请输入简历内容" if language == 'zh_Hans' else "Please input resume content"
            return "", error_msg

        return resume_content, ""

    def _optimize_resume_with_llm(self, resume_content: str, target_position: str, detected_issues: str, language: str) -> str:
        """Use LLM to generate resume optimization suggestions."""
        import json
        import traceback

        try:
            # Build detected issues section
            detected_issues_section = ""
            issues_fix_section = ""

            if detected_issues:
                if language == 'zh_Hans':
                    detected_issues_section = f"## 已检测到的问题\n\n{detected_issues}\n"
                    issues_fix_section = "\n5. **问题修复** - 针对上述检测到的问题提供具体修复建议"
                else:
                    detected_issues_section = f"## Detected Issues\n\n{detected_issues}\n"
                    issues_fix_section = "\n5. **Issue Resolution** - Specific fixes for the detected issues above"

            # Build prompt using template
            prompt_template = self.PROMPTS.get(language, self.PROMPTS['zh_Hans'])
            prompt = prompt_template.format(
                target_position=target_position,
                resume_content=resume_content,
                detected_issues_section=detected_issues_section,
                issues_fix_section=issues_fix_section
            )

            # Prepare LLM request
            prompt_messages = [UserPromptMessage(content=prompt)]

            # Use system-configured LLM (user should configure DeepSeek in Dify settings)
            # This approach follows Dify's best practices for plugin LLM usage
            llm_config = {
                "provider": "deepseek",
                "model": "deepseek-chat",
                "mode": "chat",
                "completion_params": {
                    "temperature": 0.7,
                    "max_tokens": 2000
                }
            }

            # 🔍 DEBUG: 打印配置信息
            print(f"🔍 DEBUG [resume_optimizer] LLM Config: {json.dumps(llm_config, indent=2, ensure_ascii=False)}")
            print(f"🔍 DEBUG [resume_optimizer] Prompt length: {len(prompt)} chars")
            print(f"🔍 DEBUG [resume_optimizer] Session type: {type(self.session)}")
            print(f"🔍 DEBUG [resume_optimizer] Session.model type: {type(self.session.model)}")
            print(f"🔍 DEBUG [resume_optimizer] Session.model.llm type: {type(self.session.model.llm)}")

            # Retry logic for LLM invocation
            max_retries = 3
            retry_delay = 1  # Initial delay in seconds

            for attempt in range(max_retries):
                try:
                    print(f"🔍 DEBUG [resume_optimizer] Attempt {attempt + 1}/{max_retries} - Calling LLM...")

                    # Invoke LLM
                    llm_result = self.session.model.llm.invoke(
                        model_config=LLMModelConfig(**llm_config),
                        prompt_messages=prompt_messages,
                        stream=False
                    )

                    # 🔍 DEBUG: 打印原始响应信息
                    print(f"🔍 DEBUG [resume_optimizer] llm_result type: {type(llm_result)}")
                    print(f"🔍 DEBUG [resume_optimizer] llm_result: {llm_result}")
                    if hasattr(llm_result, '__dict__'):
                        print(f"🔍 DEBUG [resume_optimizer] llm_result.__dict__: {llm_result.__dict__}")

                    # Extract result
                    if llm_result and hasattr(llm_result, 'message') and hasattr(llm_result.message, 'content'):
                        response_text = llm_result.message.content.strip()
                        print(f"🔍 DEBUG [resume_optimizer] Response text length: {len(response_text)} chars")

                        # Check for empty response
                        if not response_text:
                            if attempt < max_retries - 1:
                                print(f"⚠️ LLM returned empty optimization suggestions (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                                time.sleep(retry_delay)
                                retry_delay *= 2
                                continue
                            else:
                                print(f"❌ LLM returned empty optimization suggestions after {max_retries} attempts")
                                return "LLM调用返回空结果，请稍后重试" if language == 'zh_Hans' else "LLM returned empty result, please retry later"

                        return response_text
                    else:
                        # No valid response - retry
                        print(f"⚠️ DEBUG [resume_optimizer] Invalid response structure")
                        if attempt < max_retries - 1:
                            print(f"⚠️ LLM returned invalid response (attempt {attempt + 1}/{max_retries}), retrying in {retry_delay}s...")
                            time.sleep(retry_delay)
                            retry_delay *= 2
                            continue
                        else:
                            return "LLM调用返回空结果" if language == 'zh_Hans' else "LLM returned empty result"

                except Exception as e:
                    error_details = str(e)

                    # 🔍 DEBUG: 打印完整异常信息
                    print(f"❌ DEBUG [resume_optimizer] Exception type: {type(e).__name__}")
                    print(f"❌ DEBUG [resume_optimizer] Exception args: {e.args}")
                    print(f"❌ DEBUG [resume_optimizer] Full traceback:\n{traceback.format_exc()}")

                    # 尝试获取更多异常信息
                    if hasattr(e, 'response'):
                        print(f"❌ DEBUG [resume_optimizer] e.response: {e.response}")
                    if hasattr(e, '__cause__'):
                        print(f"❌ DEBUG [resume_optimizer] e.__cause__: {e.__cause__}")
                    if hasattr(e, '__context__'):
                        print(f"❌ DEBUG [resume_optimizer] e.__context__: {e.__context__}")

                    # Check if it's a configuration error (don't retry)
                    if "Provider" in error_details and "does not exist" in error_details:
                        return f"请在Dify设置中配置DeepSeek提供商: {error_details}" if language == 'zh_Hans' else f"Please configure DeepSeek provider in Dify settings: {error_details}"

                    # For other errors, retry
                    if attempt < max_retries - 1:
                        print(f"⚠️ LLM invocation failed (attempt {attempt + 1}/{max_retries}): {error_details}, retrying in {retry_delay}s...")
                        time.sleep(retry_delay)
                        retry_delay *= 2
                        continue
                    else:
                        print(f"❌ LLM invocation failed after {max_retries} attempts: {error_details}")
                        return f"LLM调用失败: {error_details}" if language == 'zh_Hans' else f"LLM invocation failed: {error_details}"

            # Fallback (should not reach here)
            return "LLM调用失败，请稍后重试" if language == 'zh_Hans' else "LLM invocation failed, please retry later"

        except Exception as e:
            error_details = str(e)
            print(f"❌ DEBUG [resume_optimizer] Outer exception: {traceback.format_exc()}")
            return f"优化过程出错: {error_details}" if language == 'zh_Hans' else f"Optimization error: {error_details}"

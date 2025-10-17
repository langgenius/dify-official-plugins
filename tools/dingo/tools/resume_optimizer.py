from typing import Any
from collections.abc import Generator

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
        "zh_Hans": """你是一位资深的简历优化专家。请对这份简历进行全方位优化，包括内容表达、结构布局、关键词优化等各个方面。

目标岗位：{target_position}

请针对【{target_position}】岗位提供简洁的优化要点：

## 优化建议
1. **岗位匹配度** - 关键技能匹配分析
2. **关键词优化** - 针对{target_position}的重要关键词
3. **经验突出** - 如何更好展示相关经验
4. **结构改进** - 简历布局和格式建议

请提供具体、可操作的优化要点。

简历内容：
{resume_content}""",

        "en_US": """You are a seasoned resume optimization expert. Please optimize this resume comprehensively, including content expression, structural layout, keyword optimization, and other aspects.

Target Position: {target_position}

Please provide concise optimization points for the [{target_position}] position:

## Optimization Suggestions
1. **Position Match** - Key skills alignment analysis
2. **Keyword Optimization** - Important keywords for {target_position}
3. **Experience Highlight** - How to better showcase relevant experience
4. **Structure Improvement** - Resume layout and format suggestions

Please provide specific, actionable optimization points.

Resume Content:
{resume_content}"""
    }

    def _invoke(self, tool_parameters: dict[str, Any]) -> Generator[ToolInvokeMessage]:
        """
        Invoke the resume optimizer tool.

        Args:
            tool_parameters: Tool parameters including resume_content, target_position, and language

        Returns:
            Generator of ToolInvokeMessage
        """
        try:
            # Extract and validate parameters
            target_position = tool_parameters.get('target_position', '').strip()
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
            result = self._optimize_resume_with_llm(resume_content, target_position, language)
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

    def _optimize_resume_with_llm(self, resume_content: str, target_position: str, language: str) -> str:
        """Use LLM to generate resume optimization suggestions."""
        try:
            # Build prompt using template
            prompt_template = self.PROMPTS.get(language, self.PROMPTS['zh_Hans'])
            prompt = prompt_template.format(
                target_position=target_position,
                resume_content=resume_content
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

            # Invoke LLM
            llm_result = self.session.model.llm.invoke(
                model_config=LLMModelConfig(**llm_config),
                prompt_messages=prompt_messages,
                stream=False
            )

            # Extract result
            if llm_result and hasattr(llm_result, 'message') and hasattr(llm_result.message, 'content'):
                return llm_result.message.content
            else:
                return "LLM调用返回空结果" if language == 'zh_Hans' else "LLM returned empty result"

        except Exception as e:
            error_details = str(e)
            if "Provider" in error_details and "does not exist" in error_details:
                return f"请在Dify设置中配置DeepSeek提供商: {error_details}" if language == 'zh_Hans' else f"Please configure DeepSeek provider in Dify settings: {error_details}"
            else:
                return f"LLM调用失败: {error_details}" if language == 'zh_Hans' else f"LLM invocation failed: {error_details}"

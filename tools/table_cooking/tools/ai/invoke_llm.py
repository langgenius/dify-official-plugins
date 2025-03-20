import anthropic
from google import genai
from google.genai import types
from openai import OpenAI
from pydantic import BaseModel, ValidationError, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from tenacity import *


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    # == AI == #
    # 提取语义信息
    OPENAI_API_KEY: SecretStr = ""
    ANTHROPIC_API_KEY: SecretStr = ""
    ALPHAVANTAGE_API_KEY: SecretStr = ""
    TABLE_QUERY_ENGINE_LLM: str = "qwen"
    GOOGLE_API_KEY: SecretStr = ""

    # == Qwen2.5-72B-Instruct | SGLang == #
    QWEN25_72B_INSTRUCT_BASE_URL: str = "http://192.168.1.53:30000/v1"
    QWEN25_32B_INSTRUCT_BASE_URL: str = "http://192.168.1.53:30001/v1"


settings = Settings()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((ValidationError, Exception)),
    reraise=True,
)
def invoke_qwen(
    user_content: str,
    system_prompt: str = None,
    temperature: float = 0,
    max_tokens: int = 4096,
    **kwargs,
) -> str:
    base_url = kwargs.get("base_url", settings.QWEN25_72B_INSTRUCT_BASE_URL)
    system_prompt = system_prompt or "You are a helpful AI assistant."

    client = OpenAI(api_key="none", base_url=base_url)
    completion = client.chat.completions.create(
        model="qwen",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_tokens=max_tokens,
        temperature=temperature,
    )

    assistant_content = completion.choices[0].message.content
    return assistant_content


def invoke_qwen_coder(**kwargs):
    if "base_url" in kwargs:
        del kwargs["base_url"]

    return invoke_qwen(base_url=settings.QWEN25_32B_INSTRUCT_BASE_URL, **kwargs)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((ValidationError, Exception)),
    reraise=True,
)
def invoke_qwen_with_structure_output(
    user_content: str,
    response_format: BaseModel,
    system_prompt: str = None,
    temperature: float = 0,
    max_tokens: int = 4096,
) -> BaseModel:
    client = OpenAI(api_key="none", base_url=settings.QWEN25_72B_INSTRUCT_BASE_URL)
    completion = client.beta.chat.completions.parse(
        model="qwen",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        max_tokens=max_tokens,
        response_format=response_format,
        temperature=temperature,
    )

    model = completion.choices[0].message.parsed
    return model


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((ValidationError, Exception)),
    reraise=True,
)
def invoke_claude(
    user_content: str, system_prompt: str = None, temperature: float = 0, max_tokens: int = 4096
) -> str:
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        temperature=temperature,
    )
    assistant_content = response.content[0].text
    return assistant_content


def invoke_gemini(
    user_content: str, system_prompt: str = None, temperature: float = 0, max_tokens: int = 4096
):
    client = genai.Client(api_key=settings.GOOGLE_API_KEY.get_secret_value())

    response = client.models.generate_content(
        model="gemini-2.0-flash-exp",
        contents=user_content,
        config=types.GenerateContentConfig(
            temperature=temperature, max_output_tokens=max_tokens, system_instruction=system_prompt
        ),
    )
    return response.text


def invoke_claude_debugger(natural_query: str, code: str, error_message: str):
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY.get_secret_value())

    messages = [
        {"role": "user", "content": natural_query},
        {"role": "assistant", "content": code},
        {"role": "user", "content": f"运行报错，重新给出代码。 \nerror:\n{error_message}"},
    ]
    system = """
    根据已有的代码、错误信息和辅助数据，重新输出代码。
    注意:
    - 你只能输出修改后的完整代码，不需要任何解释信息和注释
    - 你只能基于原有的代码结构和错误信息提供细节修复，不能改动函数签名和返回值类型
    """
    response = client.messages.create(
        model="claude-3-5-sonnet-20241022",
        max_tokens=4096,
        system=system,
        messages=messages,
        temperature=0.3,
    )
    assistant_content = response.content[0].text
    return assistant_content

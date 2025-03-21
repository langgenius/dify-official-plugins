import shutil
from pathlib import Path
from typing import Any, NoReturn
from typing import Optional
from urllib.parse import urlparse
from uuid import uuid4

import pandas as pd
import tiktoken
from dify_plugin.core.runtime import Session
from dify_plugin.entities.model.llm import LLMModelConfig
from dify_plugin.errors.tool import ToolProviderCredentialValidationError
from dify_plugin.file.file import File
from loguru import logger
from pydantic import BaseModel, UUID4

from tools.ai.table_self_query import TableQueryEngine, QueryResult
from tools.pipeline.constant import ARTIFACT_FILES_DIR

PREVIEW_CODE_WRAPPER = """
<segment table="{table_name}">
<question>{question}</question>
<code>
{query_code}
</code>
<output filename="{recommend_filename}">
{result_markdown}
</output>
</segment>
"""

encoding = tiktoken.get_encoding("o200k_base")


class ArtifactPayload(BaseModel):
    task_id: UUID4

    natural_query: str
    """
    Natural language query description.
    Todo: In multiple rounds of dialogue, this should be a semantic complete query after being spliced by the memory model.
    """

    name: str
    """
    filename
    """

    mime_type: str
    """
    table mime_type
    """

    type: str
    """
    dify file type
    """

    extension: str
    """
    table extension (.csv / .xlsx / .xls)
    """

    input_table_path: Path
    """
    Temporary address of table files in plug-in, deleted after QA and not retained
    """

    dify_model_config: LLMModelConfig
    """
    Dify LLM model configuration
    """

    enable_classifier: bool = True
    """
    Start the problem classifier and let the query flow to `simple query` or `complex calculation`
    """

    # local_url: Optional[str] = Field(default="", description="artifact filepath in the Dify")
    # public_url: AnyUrl = Field(..., description="URL to download the artifact")

    @property
    def cache_dir(self) -> Path:
        return ARTIFACT_FILES_DIR.joinpath(str(self.task_id))

    @staticmethod
    def validation(tool_parameters: dict[str, Any]) -> NoReturn | None:
        query = tool_parameters.get("query")
        table = tool_parameters.get("table")
        chef = tool_parameters.get("chef")

        # !!<LLM edit>
        if not query or not isinstance(query, str):
            raise ToolProviderCredentialValidationError("Query is required and must be a string.")
        if not table or not isinstance(table, File):
            raise ToolProviderCredentialValidationError("Table is required and must be a file.")
        if table.extension not in [".csv", ".xls", ".xlsx"]:
            raise ToolProviderCredentialValidationError("Table must be a csv, xls, or xlsx file.")

        # Check if the URL is of string type
        if not isinstance(table.url, str):
            raise ToolProviderCredentialValidationError("URL must be a string.")

        # Parses URL and verify scheme
        parsed_url = urlparse(table.url)
        if parsed_url.scheme not in ["http", "https"]:
            scheme = parsed_url.scheme or "missing"
            raise ToolProviderCredentialValidationError(
                f"Invalid URL scheme '{scheme}'. FILES_URL must start with 'http://' or 'https://'."
                f"Please check more details https://github.com/langgenius/dify/blob/72191f5b13c55b44bcd3b25f7480804259e53495/docker/.env.example#L42"
            )
        # !!</LLM edit>

        # Prevent stupidity
        not_available_models = [
            "gpt-4.5-preview",
            "gpt-4.5-preview-2025-02-27",
            "o1",
            "o1-2024-12-17",
            "o1-pro",
            "o1-pro-2025-03-19",
        ]
        if (
            isinstance(chef, dict)
            and chef.get("model_type", "") == "llm"
            and chef.get("provider", "") == "langgenius/openai/openai"
            and chef.get("mode", "") == "chat"
        ):
            if use_model := chef.get("model"):
                if use_model in not_available_models:
                    raise ToolProviderCredentialValidationError(
                        f"Model `{use_model}` is not available for this tool. "
                        f"Please replace other cheaper models."
                    )

    @classmethod
    def from_dify(cls, tool_parameters: dict[str, Any]):
        query = tool_parameters.get("query")
        table = tool_parameters.get("table")
        dify_model_config = tool_parameters.get("chef")

        ArtifactPayload.validation(tool_parameters)

        task_id = uuid4()
        content = table.blob

        if isinstance(dify_model_config, dict):
            dify_model_config = LLMModelConfig(**dify_model_config)

        # Generate filename based on content hash
        cache_dir = ARTIFACT_FILES_DIR.joinpath(str(task_id))
        cache_dir.mkdir(exist_ok=True, parents=True)

        filepath = cache_dir.joinpath(f"{str(uuid4())}{table.extension}")
        filepath.write_bytes(content)

        return cls(
            task_id=task_id,
            natural_query=query,
            name=table.filename,
            mime_type=table.mime_type,
            type=str(table.type),
            extension=table.extension,
            input_table_path=filepath,
            dify_model_config=dify_model_config,
        )

    def release_cache(self):
        """Delete the cache directory for this task"""
        if isinstance(self.input_table_path, Path) and self.input_table_path.is_file():
            cache_dir = self.input_table_path.parent

            # Anti-dust operation
            if not cache_dir.is_dir() or cache_dir.parent.name != "artifact_files":
                return

            try:
                shutil.rmtree(cache_dir, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Failed to delete cache file {cache_dir}: {e}")


def transform_friendly_prompt_template(
    question: str, table_name: str, query_code: str, recommend_filename: str, result_data: Any
):
    preview_df = pd.DataFrame.from_records(result_data)
    result_markdown = preview_df.to_markdown(index=False)
    wrapper_ = PREVIEW_CODE_WRAPPER.format(
        question=question,
        table_name=table_name,
        query_code=query_code,
        recommend_filename=recommend_filename,
        result_markdown=result_markdown,
    ).strip()

    return wrapper_, result_markdown


def transform_to_dify_file(
    recommend_filename: str,
    artifact_extension: str,
    result_data: Any,
    *,
    storage_dir: Optional[Path],
):
    flag = Path(recommend_filename).stem
    flag2 = str(uuid4())

    data_path = storage_dir.joinpath(f"{flag}/{flag2}{artifact_extension}")
    df = pd.DataFrame.from_records(result_data)
    if artifact_extension in [".csv"]:
        df.to_csv(str(data_path), index=False)
    elif artifact_extension in [".xlsx", ".xls"]:
        df.to_excel(str(data_path), index=False, sheet_name=flag)

    return data_path


class CodeInterpreter(BaseModel):
    code: str


class CookingResultParams(BaseModel):
    code: str
    natural_query: str
    recommend_filename: str
    input_tokens: int
    input_table_name: str


class CookingResult(BaseModel):
    llm_ready: str
    human_ready: str
    params: CookingResultParams


@logger.catch
def table_self_query(artifact: ArtifactPayload, session: Session) -> CookingResult:
    engine = TableQueryEngine(session=session, dify_model_config=artifact.dify_model_config)
    engine.load_table(artifact.input_table_path)

    result: QueryResult = engine.query(artifact.natural_query)
    if result.error:
        logger.error(result.error)

    recommend_filename = result.get_recommend_filename(suffix=".md")

    # 将 segment 压缩成 LLM_READY 的 XML_CONTENT
    # 但由于查询结果数据量可能非常大，不宜将完整内容插入会话污染上下文
    # 也许最佳实践的方式是插入 preview lines 以及资源预览链接
    __xml_context__, __preview_context__ = transform_friendly_prompt_template(
        question=artifact.natural_query,
        table_name=artifact.name,
        query_code=result.query_code,
        recommend_filename=recommend_filename,
        result_data=result.data,
    )

    # Excessively long text should be printed directly instead of output by LLM
    input_tokens = len(encoding.encode(__xml_context__))

    # Return to the table preview file after operation
    # transform_to_dify_file(
    #     recommend_filename=recommend_filename,
    #     artifact_extension=artifact.extension,
    #     result_data=result.data,
    #     storage_dir=artifact.cache_dir,
    # )

    return CookingResult(
        llm_ready=__xml_context__,
        human_ready=__preview_context__,
        params=CookingResultParams(
            code=result.query_code,
            natural_query=artifact.natural_query,
            recommend_filename=recommend_filename,
            input_tokens=input_tokens,
            input_table_name=artifact.name,
        ),
    )

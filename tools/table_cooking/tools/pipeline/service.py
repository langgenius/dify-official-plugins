import hashlib
from pathlib import Path
from typing import Dict, Any
from typing import Optional, List, Tuple
from uuid import uuid4

import pandas as pd
import tiktoken
from dify_plugin.core.runtime import Session
from dify_plugin.entities.model.llm import LLMModelConfig
from dify_plugin.file.file import File
from loguru import logger
from pydantic import BaseModel, Field

from tools.ai.table_self_query import TableQueryEngine, QueryResult
from tools.pipeline.constant import ARTIFACT_FILES_DIR

PREVIEW_CODE_WRAPPER = """
<segment>
<question>{question}</question>
<question_type>{question_type}</question_type>
<code>
{query_code}
</code>
<output filename="{recommend_filename}">
{result_markdown}
</output>
</segment>
"""


class ArtifactPayload(BaseModel):
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

    filepath: Path
    """
    Temporary address of table files in plug-in, deleted after QA and not retained
    """

    model_config: LLMModelConfig
    """
    Dify LLM model configuration
    """

    enable_classifier: bool = True
    """
    Start the problem classifier and let the query flow to `simple query` or `complex calculation`
    """

    # local_url: Optional[str] = Field(default="", description="artifact filepath in the Dify")
    # public_url: AnyUrl = Field(..., description="URL to download the artifact")

    @classmethod
    def from_dify_tool_parameters(
        cls, query: str, table: File, model_config: LLMModelConfig | dict
    ):
        content = table.blob

        if isinstance(model_config, dict):
            model_config = LLMModelConfig(**model_config)

        # Generate filename based on content hash
        content_hash = hashlib.sha256(content).hexdigest()
        cache_dir = ARTIFACT_FILES_DIR
        cache_dir.mkdir(exist_ok=True, parents=True)

        filepath = cache_dir.joinpath(f"{content_hash}{table.extension}")
        filepath.write_bytes(content)

        return cls(
            natural_query=query,
            name=table.filename,
            mime_type=table.mime_type,
            type=str(table.type),
            extension=table.extension,
            filepath=filepath,
            model_config=model_config,
        )

    def release_cache(self):
        if isinstance(self.filepath, Path) and self.filepath.is_file():
            try:
                self.filepath.unlink(missing_ok=True)
            except Exception as e:
                logger.warning(f"Failed to delete cache file {self.filepath}: {e}")


class Segment(BaseModel):
    natural_query: str
    code: str
    output_content: str
    result_data: List[Dict[str, Any]]
    question_type: str = Field(default="")
    recommend_filename: Optional[str] = Field(default="output.xlsx")
    artifact_extension: str

    def to_llm_friendlly_xml_segment(self, head_n: int = 5) -> Tuple[str, str]:
        preview_df = pd.DataFrame.from_records(self.result_data).head(head_n)
        preview_markdown = preview_df.to_markdown(index=False)

        wrapper_ = PREVIEW_CODE_WRAPPER.format(
            question=self.natural_query,
            question_type=self.question_type,
            query_code=self.code,
            recommend_filename=self.recommend_filename,
            result_markdown=preview_markdown,
        ).strip()

        wrapper_log = PREVIEW_CODE_WRAPPER.format(
            question=self.natural_query,
            question_type=self.question_type,
            query_code=self.code,
            recommend_filename=self.recommend_filename,
            result_markdown=preview_markdown,
        ).strip()

        return wrapper_, preview_markdown

    def storage_to_local(self, *, storage_dir: Optional[Path]):
        wrapper_ = PREVIEW_CODE_WRAPPER.format(
            question=self.natural_query,
            question_type=self.question_type,
            query_code=self.code,
            recommend_filename=self.recommend_filename,
            result_markdown=self.output_content,
        ).strip()

        flag = Path(self.recommend_filename).stem
        flag2 = str(uuid4())

        xml_path = storage_dir.joinpath(f"{flag}/{flag2}.xml")
        xml_path.parent.mkdir(exist_ok=True, parents=True)
        xml_path.write_text(wrapper_, encoding="utf8")

        data_path = storage_dir.joinpath(f"{flag}/{flag2}{self.artifact_extension}")
        if self.artifact_extension in [".csv"]:
            pd.DataFrame.from_records(self.result_data).to_csv(str(data_path), index=False)
        elif self.artifact_extension in [".xlsx", ".xls"]:
            pd.DataFrame.from_records(self.result_data).to_excel(
                str(data_path), index=False, sheet_name=flag
            )

        return xml_path, data_path


class CodeInterpreter(BaseModel):
    code: str


encoding = tiktoken.get_encoding("o200k_base")


@logger.catch
def table_self_query(artifact: ArtifactPayload, session: Session, **kwargs) -> Dict[str, Any]:
    engine = TableQueryEngine(session=session, dify_model_config=artifact.model_config)
    engine.load_table(artifact.filepath)

    logger.info(f"Input question: {artifact.natural_query}")

    result: QueryResult = engine.query(artifact.natural_query)
    if result.error:
        logger.error(result.error)

    segment = Segment(
        natural_query=artifact.natural_query,
        code=result.query_code,
        output_content=pd.DataFrame.from_records(result.data).to_markdown(index=False),
        result_data=result.data,
        question_type=result.query_type,
        recommend_filename=result.get_recommend_filename(suffix=".md"),
        artifact_extension=artifact.extension,
    )

    # 将 segment 压缩成 LLM_READY 的 XML_CONTENT
    # 但由于查询结果数据量可能非常大，不宜将完整内容插入会话污染上下文
    # 也许最佳实践的方式是插入 preview lines 以及资源预览链接
    __xml_context__, __preview_context__ = segment.to_llm_friendlly_xml_segment(head_n=5)

    # 计算tokens，过长的文本应直接打印而不是通由 LLM 输出
    input_tokens = len(encoding.encode(__xml_context__))

    # 将 segment 上传至 minio
    # 便于将查询结果作为 runtime_artifact 插入到会话变量中
    # xml_path, data_path = segment.storage_to_local(storage_dir=segments_dir)
    # data_download_link = get_attachment_remote_url(str(data_path), is_public=True)
    # data_preview_markdown = (
    #     f"[{result.get_recommend_filename(suffix=artifact.extension)}]({data_download_link})"
    # )

    return {
        "__xml_context__": __xml_context__,
        "__preview_context__": __preview_context__,
        "segment": {
            "code": segment.code,
            "natural_query": segment.natural_query,
            "question_type": segment.question_type,
            "recommend_filename": segment.recommend_filename,
        },
        # "data_download_link": data_download_link,
        # "data_preview_markdown": data_preview_markdown,
        "input_tokens": input_tokens,
    }

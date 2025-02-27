import logging
from collections.abc import Generator
from typing import Any

import nest_asyncio
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File
from llama_cloud_services import LlamaParse
from llama_cloud_services.parse.utils import ResultType
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class ToolParameters(BaseModel):
    files: list[File]
    result_type: ResultType
    num_workers: int
    verbose: bool
    language: str


mime_type_map = {
    ResultType.JSON: "application/json",
    ResultType.MD: "text/markdown",
    ResultType.TXT: "text/plain",
}


class LlamaParseTool(Tool):
    """
    A tool for parsing text using Llama Cloud Services
    """

    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        nest_asyncio.apply()
        if tool_parameters.get("files") is None:
            raise ValueError("File is required")
        params = ToolParameters(**tool_parameters)
        files = params.files

        parser = LlamaParse(
            api_key=self.runtime.credentials.get("llama_cloud_api_key", ""),
            result_type=params.result_type,
            num_workers=params.num_workers,
            verbose=params.verbose,
            language=params.language,
            ignore_errors=False,
        )
        for file in files:
            documents = parser.load_data(
                file_path=file.blob,
                extra_info={"file_name": file.filename},
            )
            texts = "---".join([doc.text for doc in documents])
            yield self.create_text_message(texts)
            handled_docs = [
                {"text": doc.text, "metadata": doc.metadata} for doc in documents
            ]
            yield self.create_json_message({file.filename: handled_docs})
            yield self.create_blob_message(
                texts.encode(),
                meta={
                    "mime_type": mime_type_map[params.result_type],
                },
            )

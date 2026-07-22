import io
import logging
from collections.abc import Generator
from typing import Any

import pandas as pd
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File

logger = logging.getLogger(__name__)


def _get_cell_by_column(row: pd.Series, column: Any) -> Any:
    if isinstance(column, str):
        column = column.strip()

    if column in row.index:
        return row.loc[column]

    if isinstance(column, int):
        return row.iloc[column]

    if isinstance(column, float) and column.is_integer():
        return row.iloc[int(column)]

    if isinstance(column, str) and column.isdigit():
        return row.iloc[int(column)]

    return row.loc[column]


class QAChunkTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        """
        invoke general chunk tool
        """
        file: File | None = tool_parameters.get("input_file", None)
        if not file:
            yield self.create_text_message("No input file provided")
            return
        
        if not file.filename or not file.filename.endswith(".csv"):
            yield self.create_text_message("Input file must be a CSV file")
            return
        
        question_column = tool_parameters.get("question_column", 0)
        answer_column = tool_parameters.get("answer_column", 1)
        
        try:
            file_stream = io.BytesIO(file.blob)

            df = pd.read_csv(file_stream, encoding='utf-8')
        except UnicodeDecodeError:
            file_stream.seek(0)
            try:
                df = pd.read_csv(file_stream, encoding='gbk')
            except Exception as e:
                file_stream.seek(0)
                df = pd.read_csv(file_stream, encoding='latin-1')
        except Exception as e:
            logger.error(f"Get CSV file failed: {e}", exc_info=True)
            yield self.create_text_message(f"Get CSV file failed: {e}")
            return
        qa_chunks = []
        try:
            for _, row in df.iterrows():
                question = str(_get_cell_by_column(row, question_column))
                answer = str(_get_cell_by_column(row, answer_column))
                qa_chunks.append({"question": question, "answer": answer})
        except (IndexError, KeyError) as e:
            yield self.create_text_message(
                f"Column not found: {e}. Available columns: {list(df.columns)}"
            )
            return
        
        result = {
            "qa_chunks": qa_chunks,
        }
        try:
            yield self.create_variable_message("result", result)
        except Exception as e:
            yield self.create_text_message(f"Error: {e}")

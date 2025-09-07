import io
from collections.abc import Generator
from typing import Any

import pandas as pd
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage
from dify_plugin.file.file import File


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
            yield self.create_text_message(f"Get CSV file failed: {e}")
            return
        qa_chunks = []
        for index, row in df.iterrows():
            question = str(row[question_column])
            answer = str(row[answer_column])
            qa_chunks.append({"question": question, "answer": answer})
        
        result = {
            "qa_chunks": qa_chunks,
        }
        try:
            yield self.create_variable_message("result", result)
        except Exception as e:
            yield self.create_text_message(f"Error: {e}")

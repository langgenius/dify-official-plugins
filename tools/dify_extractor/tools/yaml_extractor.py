"""YAML document extractor."""

import yaml

from tools.document import Document, ExtractorResult
from tools.errors import ExtractionError
from tools.extractor_base import BaseExtractor
from tools.helpers import decode_text


class YAMLExtractor(BaseExtractor):
    def extract(self) -> ExtractorResult:
        text = decode_text(self.context.file_bytes, self.context.file_name)
        if not text.strip() or all(
            not line.strip() or line.lstrip().startswith("#") for line in text.splitlines()
        ):
            raise ExtractionError(f"File '{self.context.file_name}' contains no YAML content.")
        try:
            yaml_data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            location = f" at line {mark.line + 1}, column {mark.column + 1}" if mark else ""
            raise ExtractionError(
                f"File '{self.context.file_name}' contains invalid YAML{location}."
            ) from exc

        formatted_yaml = yaml.safe_dump(
            yaml_data,
            allow_unicode=True,
            default_flow_style=False,
            indent=2,
            sort_keys=False,
        )
        md_content = f"```yaml\n{formatted_yaml}```"
        return ExtractorResult(
            md_content=md_content,
            documents=[
                Document(
                    page_content=md_content,
                    metadata={"source": self.context.file_name, "type": "yaml"},
                )
            ],
        )

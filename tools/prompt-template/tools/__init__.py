import re
from typing import Any, Generator
from dify_plugin import Tool
from dify_plugin.entities.tool import ToolInvokeMessage

_VAR_RE = re.compile(r"\{\{([^}]+)\}\}")


class PromptRenderTool(Tool):
    def _invoke(
        self, tool_parameters: dict[str, Any]
    ) -> Generator[ToolInvokeMessage, None, None]:
        system_template = tool_parameters.get("system_template", "")
        user_template = tool_parameters.get("user_template", "")
        extra_vars_raw = tool_parameters.get("extra_vars", {})
        fallback = tool_parameters.get("fallback", "")
        system_only = tool_parameters.get("system_only", False)

        # Collect all variables
        variables = {}
        for key, value in tool_parameters.items():
            if key in ("system_template", "user_template", "extra_vars", "fallback", "system_only"):
                continue
            if value is not None:
                variables[key] = str(value)

        if isinstance(extra_vars_raw, dict):
            for k, v in extra_vars_raw.items():
                if v is not None:
                    variables[k] = str(v)

        renderer = lambda tpl: _VAR_RE.sub(
            lambda m: str(variables.get(m.group(1).strip(), fallback)), tpl
        ).strip() if tpl else ""

        if system_only:
            rendered = renderer(system_template)
            yield self.create_text_message(rendered)
            return

        system_rendered = renderer(system_template)
        user_rendered = renderer(user_template)

        yield self.create_text_message(system_rendered)
        yield self.create_text_message(user_rendered)

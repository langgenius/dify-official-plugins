"""
Typed output variables for workflow nodes.

Each tool declares its variables once, in the ``output_schema`` of its YAML (that is
what lets later workflow nodes pick them in the editor). ``@with_outputs`` reads that
schema and guarantees every declared variable is emitted on every path:

- the tool fills ``self._out`` with the values it has (``success=True`` when it finished);
- anything not filled gets an empty value of its declared type ("", 0, false, [], {});
- ``success`` is false and ``error`` holds the last text message when the tool stopped
  early, so a workflow can branch on ``success`` instead of parsing ``text``.

The existing ``text`` and ``json`` outputs are unchanged; the variables are additive.
"""

import copy
import functools
import inspect
from pathlib import Path
from typing import Any, Callable

import yaml

_EMPTY: dict[str, Any] = {"string": "", "integer": 0, "number": 0, "boolean": False, "object": {}, "array": []}


def declared_outputs(tool_file: str) -> dict[str, Any]:
    """Variable name -> empty value, from the output_schema of the YAML next to the tool's .py file."""
    spec = yaml.safe_load(Path(tool_file).with_suffix(".yaml").read_text(encoding="utf-8")) or {}
    properties = (spec.get("output_schema") or {}).get("properties") or {}
    # "array[object]" and "array" both start empty.
    return {name: copy.deepcopy(_EMPTY.get(str(p.get("type", "")).split("[")[0])) for name, p in properties.items()}


def with_outputs(invoke: Callable) -> Callable:
    """Decorate a Tool._invoke so it ends by emitting every variable its output_schema declares."""
    declared: dict[str, Any] | None = None

    @functools.wraps(invoke)
    def wrapper(self, tool_parameters: dict[str, Any]):
        nonlocal declared
        if declared is None:
            declared = declared_outputs(inspect.getfile(invoke))
        self._out = {}
        texts: list[str] = []
        create_text = self.create_text_message

        def recording(text: str):
            texts.append(text)
            return create_text(text)

        self.create_text_message = recording
        try:
            yield from invoke(self, tool_parameters)
        finally:
            self.create_text_message = create_text

        success = bool(self._out.get("success"))
        values = copy.deepcopy(declared)
        values.update({k: v for k, v in self._out.items() if k in values})
        if "success" in values:
            values["success"] = success
        if "error" in values:
            values["error"] = "" if success else str(self._out.get("error") or (texts[-1] if texts else "The tool did not finish."))
        for name, value in values.items():
            yield self.create_variable_message(name, value)

    return wrapper

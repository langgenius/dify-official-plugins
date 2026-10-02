"""Regression tests for the removal of the stale ``models/anthropic/schemas/model-schema.json`` file.

Background:
    Commit 8e927b67 ("feat(anthropic): add claude-fable-5 models with adaptive thinking support",
    #3269) added ``models/anthropic/schemas/model-schema.json`` plus a
    ``# yaml-language-server: $schema=../../schemas/model-schema.json`` header
    comment to four model YAMLs. The JSON schema file's ``$id`` was set to
    ``https://jhlfund.com/schemas/dify-model.yaml.json`` — a domain unrelated
    to Anthropic. The Dify marketplace extracts outbound hosts from source
    files and listed ``jhlfund.com`` as a host the plugin accesses, which
    looked suspicious to users even though the plugin never made any
    request to that domain (the schema was never imported in source code
    and only existed as an IDE auto-completion hint via the YAML header
    comments).

    See https://github.com/langgenius/dify-official-plugins/issues/3994.

These tests guard against the file or domain being re-introduced.

The tests are pure file-system and source-text inspection — no SDK or
network access is required.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT_DIR / "schemas" / "model-schema.json"


def test_stale_schema_file_is_removed() -> None:
    """The stale ``schemas/model-schema.json`` file must not exist.

    Pre-fix the marketplace extraction picked up ``https://jhlfund.com`` from
    the file's ``$id`` field. The file was never imported anywhere in the
    source code — it only existed as an IDE auto-completion hint via
    ``# yaml-language-server: $schema=...`` comments on four model YAMLs.
    Those comments have been removed in the same change; this test guards
    against the file being re-introduced (with or without the suspicious
    domain).
    """
    assert not SCHEMA_PATH.exists(), (
        f"stale schema file still exists at {SCHEMA_PATH}; the Dify marketplace "
        "extracts outbound hosts from source files and listed jhlfund.com as a "
        "host the plugin accesses (see issue #3994)."
    )


def test_no_jhlfund_com_reference_in_anthropic_source() -> None:
    """No source file under ``models/anthropic/`` may reference ``jhlfund.com``.

    This guards against the suspicious domain being re-introduced via
    any file path (e.g. a new ``$id`` field, a comment, a hard-coded
    URL, or a documentation link). The plugin has no legitimate need to
    reference that domain.
    """
    offenders: list[tuple[Path, int, str]] = []
    for path in ROOT_DIR.rglob("*"):
        if not path.is_file():
            continue
        # Skip this test file (it mentions "jhlfund.com" by name as a guard).
        if path == Path(__file__):
            continue
        # Skip compiled / cached / venv files.
        if any(part in path.parts for part in (".venv", "__pycache__", ".git")):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if "jhlfund.com" in line:
                offenders.append((path, line_no, line.strip()))
    assert offenders == [], (
        "jhlfund.com found in anthropic source files: "
        + ", ".join(f"{p}:{line_no} ({snippet!r})" for p, line_no, snippet in offenders)
    )


def test_no_yaml_files_reference_anthropic_models_schemas() -> None:
    """No model YAML under ``models/anthropic/models/llm/`` may reference the deleted schema.

    The four affected YAMLs (``claude-fable-5.yaml``,
    ``claude-fable-5-1.yaml``, ``claude-mythos-5.yaml``, ``claude-opus-5.yaml``)
    used ``# yaml-language-server: $schema=../../schemas/model-schema.json``
    as an IDE auto-completion hint. The schema has been deleted and those
    comments have been removed. This test guards against the dangling
    references being re-introduced.
    """
    pattern = re.compile(r"schemas/model-schema\.json")
    offenders: list[Path] = []
    llm_dir = ROOT_DIR / "models" / "llm"
    if not llm_dir.exists():
        return offenders
    for path in llm_dir.glob("*.yaml"):
        if pattern.search(path.read_text(encoding="utf-8")):
            offenders.append(path)
    assert offenders == [], (
        "model YAMLs still reference the deleted schemas/model-schema.json: "
        + ", ".join(str(p) for p in offenders)
    )
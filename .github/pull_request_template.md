## Summary

<!--
Link related issues (e.g. Fixes #123) and/or briefly describe why this change is needed.

⚠️ This repository is for Dify **Official** Plugins only.
For community contributions, submit to https://github.com/langgenius/dify-plugins instead.
-->



## Change Type

- [ ] Documentation / non-plugin change
- [ ] Non-LLM plugin (tools, extensions, datasource, etc.)
- [ ] LLM plugin

## Screenshots / Videos

<!--
Drag and drop images or videos directly into this box — GitHub uploads them automatically.
Show the fix, the new feature, or before/after behavior for breaking changes.

| Before | After |
| ------ | ----- |
|        |       |
-->

| Before | After |
| ------ | ----- |
|        |       |


## LLM Plugin Checklist

<!-- Only required if "LLM plugin" is checked above. Skip otherwise.
Reference: https://github.com/langgenius/dify-official-plugins/blob/main/.assets/test-examples/llm-plugin-tests/llm_test_example.md
-->

<details>
<summary>Areas affected by this change (check all that apply)</summary>

- [ ] Message flow (system messages, user ↔ assistant turn-taking)
- [ ] Tool interaction flow (multi-round usage, Agent App and Agent Node)
- [ ] Multimodal input (images, PDFs, audio, video, etc.)
- [ ] Multimodal output (images, audio, video, etc.)
- [ ] Structured output (JSON, XML, etc.)
- [ ] Token consumption metrics
- [ ] Other LLM functionality (reasoning, grounding, prompt caching, etc.)
- [ ] New models / model parameter fixes

</details>

## Version

- [ ] Bumped top-level `version` in `manifest.yaml` (not the one under `meta`)
- [ ] `dify_plugin>=0.3.0,<0.6.0` is declared in `pyproject.toml` and locked in `uv.lock` (or kept in `requirements.txt` for legacy plugins without `uv.lock`) — [SDK docs](https://github.com/langgenius/dify-plugin-sdks/blob/main/python/README.md)

<!--
Version format: MAJOR.MINOR.PATCH — each segment may be 2 digits (e.g. 10.11.22)
- MAJOR: architectural or incompatible API changes
- MINOR: new features, backward-compatible
- PATCH: bug fixes and minor improvements
-->

## Testing

<!-- At least one environment must be tested with a clean setup matching production:
Python venv aligned with `manifest.yaml`, `pyproject.toml`, and `uv.lock` (or `requirements.txt` for legacy plugins).
-->

- [ ] Local deployment — Dify version: <!-- e.g. 1.2.0 -->
- [ ] SaaS (cloud.dify.ai)

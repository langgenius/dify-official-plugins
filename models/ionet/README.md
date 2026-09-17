# IO Intelligence (io.net) model provider for Dify — WIP

> **Status: work in progress.** This plugin is not yet submitted upstream. See "TODO before
> submitting" below.

Adds [IO Intelligence](https://io.net) (by io.net) as a Dify model provider plugin.

IO Intelligence serves an OpenAI-compatible **Chat Completions** API at
`https://api.intelligence.io.solutions/api/v1` (Bearer auth; `GET /models` is public). Model IDs
are `org/name` style, e.g. `meta-llama/Llama-3.3-70B-Instruct`. API keys are issued by the
io.net cloud console: https://cloud.io.net

## Supported models (predefined)

| Model ID | Context | Vision | Tools |
|---|---|---|---|
| zai-org/GLM-5.3 | 262144 | — | yes |
| deepseek-ai/DeepSeek-V4.1-Flash | 262124 | — | yes |
| moonshotai/Kimi-K3 | 1048576 | yes | yes |
| Qwen/Qwen3.8-27B | 65536 | yes | yes |
| deepseek-ai/DeepSeek-R1-0528 | 128000 | — | yes |
| meta-llama/Llama-3.3-70B-Instruct | 128000 | — | yes |

Custom models are also supported (customizable-model): enter any model ID from the
[public catalog](https://api.intelligence.io.solutions/api/v1/models).

## TODO before submitting

- [ ] Replace the placeholder icons (`icon.svg`, `icon-dark.svg`) with official io.net brand assets
- [ ] Extend the curated model list (6 of ~35 catalog models)
- [ ] Add `uv.lock` (generated with the repo's toolchain)
- [ ] Add `test_local.py` smoke test and `README_zh_Hans.md`
- [ ] Confirm per-model pricing (currently omitted — not published per-model)
- [ ] Live-test streaming tool calls against the real endpoint

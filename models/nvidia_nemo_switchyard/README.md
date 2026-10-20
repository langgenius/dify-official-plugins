## NVIDIA NeMo Switchyard

**Author:** langgenius
**Version:** 0.0.1
**Type:** model

### Description

Routes each LLM call between a **capable** model and an **efficient** model using
[NVIDIA NeMo Switchyard](https://github.com/NVIDIA-NeMo/Switchyard). The routing library
(`nemo-switchyard`) runs inside the plugin. No separate Switchyard service is needed.

The plugin uses Switchyard's stage router, the same algorithm as its `auto` preset. It reads the
tool results in the conversation:

- No tool history, or weak signals: the efficient model answers.
- A critical error (for example out of memory), the same error repeated, or a context-compaction
  marker: the capable model answers.
- After an escalation, the capable model keeps the next 2 turns. A clean test pass ends this early.

The routing gives the most benefit to agent workloads with tool calls. Plain chat always goes to
the default tier.

### Setup

Add a model under **NVIDIA NeMo Switchyard** in Dify. The model name is the route name shown in Dify, for
example `auto`. Each route has two upstreams. Each upstream is any endpoint that speaks one of
these APIs:

| API format | Endpoint called |
| --- | --- |
| `responses` (default) | `{base_url}/responses` |
| `chat_completions` | `{base_url}/chat/completions` |

| Field | Meaning |
| --- | --- |
| Capable / Efficient base URL | Base URL ending in `/v1` |
| Capable / Efficient API key | Sent as `Authorization: Bearer <key>`. Leave empty if not needed. |
| Capable / Efficient model name | Model ID sent to that upstream |
| Capable / Efficient API format | `responses` (default) or `chat_completions`. Use `chat_completions` for servers without the Responses API. |
| Default tier | `efficient_first` (recommended) or `capable_first` (experimental) |
| Confidence threshold | 0 to 1, default 0.5 |
| Context size | Use the smaller context window of the two models |

Saving the route sends a short request to both upstreams. An error names the tier that failed.

### Behavior

- **Fallback:** if the selected upstream fails before it sends any output, the plugin tries the
  other tier.
- **Which model answered:** the `model` field of each result chunk is the upstream model that
  served it. Dify shows it in logs.
- **Sessions:** Dify does not pass a conversation ID to model plugins. The plugin derives a
  session key from the end user and the first user message. The capable hold uses this key. Two
  conversations by one user that start with the same message share routing state.
- **State is per plugin process.** Routing state lives in memory and is lost when the plugin
  restarts.
- **Reasoning:** streamed reasoning is shown in `<think>` tags. On Chat Completions upstreams,
  reasoning from earlier assistant tool-call turns is sent back as `reasoning_content`.

### Limitations

- Text and tool calls only. Images, audio, video, and documents are rejected.
- The Responses API has no `stop` parameter, so stop words are ignored for `responses` upstreams.
- `nemo-switchyard` is pre-1.0. This plugin pins version 0.3.0.

### Development

```bash
uv sync --frozen
uv run pytest tests/test_wire.py   # unit tests, no network
uv run pytest                      # also runs end-to-end tests when configured
```

The end-to-end tests run the packaged plugin with the `dify` CLI and call real upstreams. They
are skipped unless `SWITCHYARD_{CAPABLE,EFFICIENT}_{ENDPOINT_URL,API_KEY,MODEL,API_FORMAT}` are
set. See `tests/test_llm_invoke.py`.

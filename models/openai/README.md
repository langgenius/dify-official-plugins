# OpenAI

> [!IMPORTANT]
> Version 1.0 is a major rewrite of the plugin runtime, model catalog, and test suite.
> It replaces the underlying request and streaming logic, removes deprecated model configurations, and adds focused coverage for reasoning, tool calls, multimodal inputs, and interleaved streams.

This plugin connects Dify to OpenAI language, embedding, moderation, speech-to-text, and text-to-speech models.

## What changed in 1.0

- The LLM integration was rewritten around the official OpenAI Python SDK.
- The Responses API is now the default for supported language models.
- Chat Completions remains available for compatible endpoints and audio-capable chat models.
- The plugin retains every OpenAI output item, including encrypted reasoning items and assistant phase metadata, for stateless replay when Dify passes the opaque payload back.
- Reasoning summaries, refusals, parallel function calls, terminal states, usage, and stream cancellation now have explicit handling.
- The model catalog was checked against OpenAI's model and deprecation documentation.
- Deprecated and unavailable model entries were removed, while missing current entries were added.
- The deprecated `gpt-4o`, `gpt-audio-mini`, and `gpt-4o-mini-tts` aliases were removed while their still-current dated snapshots remain available.
- The tests were reorganized into parameterized pytest suites with request, response, streaming, and non-LLM boundary coverage.

## Capabilities

- Text and vision generation.
- Structured outputs and function calling.
- Reasoning effort, summaries, modes, and context controls where supported by the selected model.
- URL and base64 image or document inputs through the Responses API.
- Audio input through supported Chat Completions models.
- Text embeddings.
- Text moderation through `omni-moderation-latest`.
- Speech transcription and text-to-speech streaming.

## Configure

Install the plugin and open the OpenAI provider in Dify's Model Provider settings.

Add an OpenAI API key and, when needed, an Organization ID or custom API base URL.

The API base may be entered with or without the trailing `/v1`.

Responses is the recommended protocol and the default for official models that support it.

Choose Chat Completions only for a compatible endpoint or a model whose documented API surface requires it.

`Enable request metadata` is optional and disabled by default. Turning it on attaches `dify_app_id` and `dify_source` to each request as `metadata`, so usage can be attributed to a specific Dify app.

The API only accepts metadata when storage is enabled, so enabling it also sends `store=true`, which persists requests and responses to Stored Completions on your OpenAI account. Leave it disabled if your organization forbids storage, or if you route through a proxy that rejects `store` or `metadata`.

<img src="./_assets/openai-01.png" width="400" alt="OpenAI provider configuration" />

## GPT-6 models

GPT-6 Astra, Sol, and Luna support text, vision, structured outputs, and streaming, with reasoning effort set to `medium` by default.
GPT-6 Astra requires Responses for function calling and does not support reasoning effort `none`.
GPT-6 Sol and Luna support function calling through Chat Completions only with reasoning effort `none`; use Responses to combine reasoning and tools.
Sampling and log-probability parameters are omitted when reasoning is enabled.

## Question classification with Decisions

Select `gpt-6-luna-only-for-question-classifier` in a Dify Question Classifier
node to use OpenAI's Decisions API with the upstream `gpt-6-luna` model. It uses
your existing OpenAI credentials and API base, regardless of the API Protocol
setting; no additional switch or model parameters are needed.

This adapter supports the six-message text Chat classifier template from
Graphon 0.7.0. It preserves the query, conversation history, category IDs and
custom instructions, and returns the existing category JSON for workflow
routing. Ordinary chat prompts, images, tools, stop sequences and generation
parameters are unsupported. Dify does not restrict this model to classifier
selectors, so its label states the intended use and the plugin validates the
message protocol. Unknown templates, invalid category results and refusals
raise errors instead of selecting a default branch. Confidence and option
probabilities are not exposed by the current classifier contract.

Decisions returns a complete result, which Dify's plugin SDK wraps into one
chunk when streaming is requested. Billing uses the API's actual token usage
at the base Decisions rate of USD 0.10 per million input tokens and zero output
cost. Regional and long-context premiums are not represented by Dify's static
pricing. Request metadata and storage options apply only to Chat/Responses,
and are not sent to Decisions.

See the [official Decisions guide](https://developers.openai.com/api/docs/guides/decisions).

## Reasoning state

The plugin sends `store=false` by default and requests encrypted reasoning content when it uses the Responses API. Enabling `Enable request metadata` switches `store` to `true`, but encrypted reasoning content is still requested, so reasoning replay behaves the same either way.

Complete response output items are stored in the assistant message's opaque payload and replayed in original order when that payload returns on the next turn.
Existing SDK, daemon, Dify, and Agent paths can lose or reject this payload during tool continuations; adding GPT-6 model support does not resolve those limitations.

Reasoning summaries are user-visible only when `reasoning_summary` is enabled for a supported model.

OpenAI may require organization verification before returning reasoning summaries.

## Development

Install the locked environment and run the checks from this directory.

```bash
uv sync --locked
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

### Live OpenAI API tests

The tests in `tests/live` send billable requests to the real OpenAI API whenever a nonempty `OPENAI_API_KEY` is available.

They skip dynamically only when the key is missing, empty, or whitespace-only in both `.env` and the process environment.

Create a local `.env` in this plugin directory for test credentials.

```dotenv
OPENAI_API_KEY=your-api-key
# OPENAI_ORGANIZATION=org-id
# OPENAI_BASE_URL=https://api.openai.com/v1
```

The test harness reads only those OpenAI variables from `.env`, and explicit process environment variables take precedence.

The repository ignores `.env`; never commit it or include its values in test output.

Run the complete matrix.

```bash
uv run pytest tests/live
```

The complete matrix sends one logical request for every configured model plus focused boundary requests, and the tool replay scenario sends a second request.

The OpenAI SDK may retry transient failures, so actual HTTP attempts can exceed the logical request count.

It should be run serially because parallel execution increases both spend and rate-limit pressure.

Use standard pytest node IDs or `-k` expressions to focus the matrix while developing.

The following smoke command sends one short request.

```bash
uv run pytest \
  'tests/live/test_llm.py::test_every_presented_llm_accepts_a_minimal_request[gpt-4o-mini]'
```

The presentation matrix gives every LLM in `models/llm/_position.yaml` one minimal request, using streaming whenever the model contract supports it.

Embedding, moderation, speech-to-text, and text-to-speech tests are derived from every YAML configuration in their respective model directories.

Representative models separately cover Responses and Chat Completions, streaming and non-streaming, structured output, reasoning summaries, streamed function calls, encrypted reasoning replay, stop and incomplete states, and image, document, and audio inputs.

Exact event interleavings, fragmented tool arguments, empty reasoning blocks, failures, cancellation, and malformed responses remain in deterministic unit tests because a live service cannot reliably reproduce those event orders.

Cases blocked only by OpenAI organization verification are reported as skips; all other API errors fail the run.

Reasoning summary coverage may also be skipped when OpenAI accepts the request but withholds the summary from an unverified organization.

## Official references

- [Model catalog](https://developers.openai.com/api/docs/models)
- [Model guidance](https://developers.openai.com/api/docs/guides/latest-model)
- [Responses API migration](https://developers.openai.com/api/docs/guides/migrate-to-responses)
- [Reasoning](https://developers.openai.com/api/docs/guides/reasoning)
- [Function calling](https://developers.openai.com/api/docs/guides/function-calling)
- [Embeddings](https://developers.openai.com/api/docs/guides/embeddings)
- [Speech to text](https://developers.openai.com/api/docs/guides/speech-to-text)
- [Text to speech](https://developers.openai.com/api/docs/guides/text-to-speech)
- [Deprecations](https://developers.openai.com/api/docs/deprecations)
- [Pricing](https://developers.openai.com/api/docs/pricing)

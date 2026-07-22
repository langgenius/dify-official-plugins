# Gemini tests

The Gemini plugin has offline unit tests and opt-in live tests that call the real Google API.

## Offline tests

Offline tests do not require credentials or make billable requests.

```bash
uv run --frozen python -m pytest -m "not live"
```

They cover request construction, message conversion, model schemas, parameter validation, file handling, structured output, and tool-call ID preservation.

## Live-test setup

Copy the example environment file and provide a Google AI Studio API key.

```bash
cp .env.example .env
```

Set these values in `.env`.

```dotenv
GEMINI_API_KEY=your-google-api-key
RUN_GEMINI_LIVE=1
```

Live tests always require `RUN_GEMINI_LIVE=1` to prevent accidental billable requests in local and CI environments.

## Run live tests

Run the complete live suite.

```bash
uv run --frozen python -m pytest -m live -v -s
```

Run only the new Gemini LLM coverage.

```bash
uv run --frozen python -m pytest models/tests/test_llm_live.py -v -s
```

Run embedding live tests.

```bash
uv run --frozen python -m pytest models/tests/test_embedding_live.py -v -s
```

Run document filtering integration tests.

```bash
uv run --frozen python -m pytest models/tests/test_document_filtering.py -m live -v -s
```

## New-model live coverage

Both `gemini-3.6-flash` and `gemini-3.5-flash-lite` are tested through the plugin LLM interface.

The live suite covers streaming text generation, non-streaming structured output, inline image input, forced function calling, call ID preservation, function responses, and multi-turn replay.

Responses are intentionally short to limit API cost.

## Troubleshooting

Skipped live tests mean the API key or the local opt-in flag is missing.

Authentication and model-access failures are test failures once live testing is explicitly enabled.

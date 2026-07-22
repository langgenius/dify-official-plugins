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

Set this value in `.env`.

```dotenv
GEMINI_API_KEY=your-google-api-key
```

Pytest automatically loads `.env` and skips live tests when `GEMINI_API_KEY` is empty or missing.

If a configured key is rejected by Google, the live test fails instead of hiding the authentication error as a skip.

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

Live tests skip only when the API key is empty or missing.

Authentication and model-access failures are test failures when an API key is configured.

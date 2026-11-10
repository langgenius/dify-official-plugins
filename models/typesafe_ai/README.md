# TypeSafe AI

Use `jev-1.13.0-only-for-question-classifier` in an existing Dify Question Classifier node. Configure the provider with your TypeSafe AI API key, then select this model; category IDs and workflow branches stay unchanged. Upstream requests use `jev-1.13.0`.

## Compatibility

This adapter accepts only the six-message text Chat template from **Graphon 0.7.0** (Dify reference revision `336dd0b8c0`), with plain strings or single text blocks. Other templates, Completion mode, images, tool calls, stop sequences and implementation-level model parameters are unsupported. Dify may remove images before the plugin receives them. The interface supplies no trusted node identity: a caller reproducing the same protocol is indistinguishable from the classifier.

The query and instruction are preserved verbatim, including quotes, backslashes and whitespace. Categories are decoded as JSON; repeated field delimiters and invalid/duplicate IDs fail explicitly before any request. History remains text. Unknown response IDs and service failures raise errors rather than selecting the first category. A single category is returned locally with zero usage.

Jev receives only query, history, custom instructions and category IDs/descriptions, not the fixed classification examples. The response contains `category_id` and `category_name`; confidence and probabilities are not exposed. GPT-2 token counting is only a local budget estimate. Billing uses actual upstream tokens at USD 0.042 per million input tokens and zero output cost. Requests use a 30-second HTTP timeout and the SDK default retries; this is not a 30-second total deadline.

## Development

Requires Python 3.12 or newer; the plugin runner uses Python 3.12.

```sh
uv sync --frozen
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

After dependency changes, run `uv lock`. Regenerate the optional compatibility file using `uv export --frozen --no-dev --no-hashes --format requirements-txt --output-file requirements.txt`. Package from the parent directory with `dify plugin package typesafe_ai`.

No credentials belong in source control. The runtime requires the Dify provider credential and does not read a workspace API key. No deployed Dify instance is needed for the local transport-level tests; full workflow deployment must be verified in the target Dify installation.

# NVIDIA API Compatible (Dify plugin)

Use any NVIDIA model from [build.nvidia.com](https://build.nvidia.com) or a self-hosted NIM in Dify,
without hard-coding model names or endpoints. Each model is added from the Dify UI
(**Settings → Model Provider → NVIDIA API Compatible → Add Model**) with its own
Model Type, Model Name, API Key, API Base URL and type-specific request parameters.

Supported model types (v0.1.0): **LLM**, **Text Embedding**, **Rerank**.

## Fields

| Field | Model type | Sent as | Notes |
|---|---|---|---|
| API Key | all | `Authorization: Bearer …` | `nvapi-…` key. Stored by Dify, never in this repo. |
| API Base URL | all | — | Default `https://integrate.api.nvidia.com/v1` |
| model name for API endpoint | all | `model` | Optional override of Model Name |
| Extra Body (JSON) | all | merged into the body | e.g. `{"nvext": {"top_k": 1}}`. Cannot override `model`, `messages`, `prompt`, `input`, `query`, `passages`, `documents`, `stream`. |
| Input type for documents | Text Embedding | `input_type` | Default `passage` (used when indexing a knowledge base). Empty = not sent. |
| Input type for queries | Text Embedding | `input_type` | Default `query` (used for retrieval). Empty = not sent. |
| Truncate | Text Embedding | `truncate` | `NONE` / `START` / `END` / Not set |
| Modality | Text Embedding | `modality` | Not set / `text` |
| Output dimensions | Text Embedding | `dimensions` | Optional; re-index after changing it |
| Model max chunks per batch | Text Embedding | — | Texts per request. Default 1: the hosted endpoint randomly returns 500 when a request exceeds ~1000 tokens. Raise for self-hosted NIM. |
| Embedding encoding format | Text Embedding | `encoding_format` | Default `float` |
| Rerank Endpoint URL | Rerank | — | Full URL from the model's code sample, e.g. `https://ai.api.nvidia.com/v1/retrieval/nvidia/llama-3_2-nv-rerankqa-1b-v2/reranking`. Empty = Base URL + `/ranking` |
| Rerank API format | Rerank | — | `NVIDIA` (`query.text` / `passages` / `rankings[].logit`, score = sigmoid(logit)) or `Cohere/Jina` (`/rerank`) |
| Truncate | Rerank | `truncate` | `NONE` / `END` / Not set (NVIDIA format only) |

All LLM fields of the upstream OpenAI-API-compatible plugin (completion mode, context size,
function calling, vision, thinking mode, …) are kept.

## Example: `nvidia/nemotron-3.5-embed-8b`

- Model Type: Text Embedding
- Model Name: `nvidia/nemotron-3.5-embed-8b`
- API Base URL: `https://integrate.api.nvidia.com/v1`
- Model context size: `32768`, max chunks: `1`
- Input type for documents: `passage`, for queries: `query`, Truncate: `END`

Request sent when indexing:

```json
{"model": "nvidia/nemotron-3.5-embed-8b", "input": ["..."], "encoding_format": "float",
 "input_type": "passage", "truncate": "END"}
```

## Development

```bash
uv sync
uv run pytest -q
# remote debug against a local Dify: copy .env.example to .env, fill REMOTE_INSTALL_KEY, then
uv run python -m main
# package (from the models/ directory)
dify plugin package ./nvidia_api_compatible
```

Based on `models/openai_api_compatible` from langgenius/dify-official-plugins (Apache-2.0).

# Voyage

Voyage model provider for Dify.

This plugin enables Dify to use Voyage text embedding and rerank models.

## Requirements

`dify_plugin >= 0.10.0` is a hard floor. Earlier SDK releases dropped `input_type`
between Dify and the plugin, so every search query was embedded with Voyage's
*document* prompt instead of its *query* prompt. Voyage's two prompts are not
interchangeable and the mismatch costs most of the retrieval quality.

## Models

| Model | Context | Dimensions | Notes |
|---|---|---|---|
| `voyage-4-large` | 32K | 1024 (256 / 512 / 2048) | best general-purpose retrieval |
| `voyage-4` | 32K | 1024 (256 / 512 / 2048) | |
| `voyage-4-lite` | 32K | 1024 (256 / 512 / 2048) | optimised for latency and cost |
| `voyage-context-4` | 32K | 1024 (256 / 512 / 2048) | contextualised chunk embeddings |
| `voyage-3.5`, `voyage-3.5-lite` | 32K | 1024 (256 / 512 / 2048) | previous generation |
| `voyage-3`, `voyage-3-large`, `voyage-3-lite` | 32K | fixed | |
| `voyage-code-2`, `voyage-code-3` | 16K / 32K | fixed | code retrieval |
| `voyage-finance-2`, `voyage-law-2`, `voyage-multilingual-2` | 16K–32K | fixed | domain models |
| `voyage-multimodal-3`, `voyage-multimodal-3.5` | 32K | fixed | text plus one image per call |
| `rerank-2.5`, `rerank-2.5-lite`, `rerank-2`, `rerank-lite-2`, `rerank-1`, `rerank-lite-1` | 32K | — | rerankers |

## Optional credentials

| Credential | Applies to | Effect |
|---|---|---|
| `output_dimension` | voyage-4 and voyage-3.5 families | Matryoshka dimension: 256, 512, 1024 or 2048. Blank uses the model default of 1024. **Changing it after a knowledge base is indexed requires a full re-index** — Dify sizes the vector store from the first vector it sees. |
| `output_dtype` | all embedding models | `float` (default), `int8`, `uint8`, `binary`, `ubinary`. Quantised types trade retrieval quality for storage. |
| `contextualize_batch` | `voyage-context-*` only | See below. |
| `image_url`, `image_base64` | `voyage-multimodal-*` only | Attaches one image to every text in the call. |

## Contextualised embeddings

`voyage-context-*` models embed a chunk with its neighbours in view, so a chunk that
says "the same procedure applies" still carries what procedure was meant. The API takes
chunks grouped by document: `inputs: [[chunk, chunk, ...], ...]`.

Dify's embedding interface passes a flat list of texts with **no indication of where one
document ends and the next begins**, so the plugin cannot reconstruct those groups. By
default each text is sent as its own single-chunk group, which is exactly equivalent to
the non-contextual endpoint and never lets one document's content bleed into another's.

Setting `contextualize_batch` to `true` sends the whole batch as one document. That is
correct only when a batch holds chunks of a single document — usually true during
ingestion, since Dify indexes one document at a time, but not guaranteed. It is never
applied to a query, which has no siblings to draw context from.

## Request batching

Every embedding model declares `max_chunks: 128`, so Dify batches 128 segments per call
instead of the framework default of 1. Because Dify picks the batch size from that number
alone and knows nothing about chunk length, the plugin re-splits each batch against
Voyage's per-request token limit before sending. Long segments therefore cost extra
requests rather than failing the ingest.

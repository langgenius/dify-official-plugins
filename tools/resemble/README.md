# Resemble Detect + Intelligence — Dify plugin

Bring **Resemble AI** deepfake detection and media intelligence into Dify. Every
capability and option is a **toggle** — you decide what runs and how.

> Scope: Detect + Intelligence only (no TTS / voice cloning).

## Tools

| Tool | What it does | Endpoint |
|---|---|---|
| **Deepfake Detection** | Analyze audio/image/video for AI-generated content. Toggle intelligence, source tracing, visualize, reverse search, OOD, zero-retention, region/frame controls, async callback. | `POST /detect` (+poll) |
| **Media Intelligence** | Transcription, translation, speaker info, emotion, context, misinformation. | `POST /intelligence` |
| **Ask About a Detection** | Natural-language Q&A grounded in a completed detection. | `POST /detects/{uuid}/intelligence` |
| **Apply Watermark** | Embed an invisible provenance watermark. | `POST /watermark/apply` |
| **Detect Watermark** | Check whether media carries a Resemble watermark. | `POST /watermark/detect` |

## Setup
1. Install the plugin in Dify.
2. Open the **Resemble Detect + Intelligence** tool provider and paste your
   **Resemble API Key** (Resemble dashboard → Account → API). Optionally override
   the API Base URL for self-hosted/enterprise.
3. Drop any tool into an agent or workflow. Media must be a **public HTTPS URL**.

## Design notes
- **Toggles, your call.** Each per-call option is a `form` field (preset by the user)
  while `url`/`query` are `llm` (an agent can fill them). So you choose exactly what
  to integrate and how.
- **Async handled for you.** Detection is asynchronous; the tools poll to completion
  (bounded by `Max Wait`). Set a `Callback URL` to run fully async instead.
- **Clean output.** Large inline base64 artifacts (e.g. heatmaps) are replaced with a
  short placeholder so results stay readable; real media URLs are preserved.

## Development & testing
- Shared API logic lives in `tools/resemble_api.py` (no Dify dependency).
- `tests/live_test.py` exercises that logic against the real API; `tests/e2e_test.py`
  imports the **actual tool classes** (via a lightweight SDK stub) and runs each
  tool's `_invoke` end-to-end. Both read `RESEMBLE_API_KEY` from the project `.env`.

```bash
python3 tests/live_test.py            # auth + detect contract
python3 tests/e2e_test.py             # all 5 tools, end-to-end, live
```

## Package
```bash
dify plugin package ./resemble        # -> resemble.difypkg
```

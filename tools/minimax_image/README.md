# MiniMax Image

Generate and edit images with [MiniMax-H3-Image](https://platform.minimax.io).

## Setup

1. Create an API key at [MiniMax International](https://platform.minimax.io) or [MiniMax China](https://platform.minimaxi.com). The two sites use separate accounts.
2. In Dify, install this plugin and open **Tools → MiniMax Image → Authorize**.
3. Paste the API key and select the matching endpoint (`api.minimax.io` or `api.minimaxi.com`).

The key is checked against the selected endpoint when you authorize (a free file-listing call), so a
mistyped key or a key from the other site is rejected there instead of failing every later run.

## Tools

- **Image Generate**: text-to-image. Optional aspect ratio (`1:1`, `16:9`, `9:16`, `4:3`, `3:4`), area (`1K` / `2K` / `4K`), and count (`n`, 1–10).
- **Image Edit**: edit 1–16 reference images with a prompt. The same aspect ratio and area options are available.

## Errors and retries

A single request can take up to 600 seconds. The API is not idempotent, so failed or timed-out
requests should not be retried automatically.

When MiniMax rejects a request (invalid key, insufficient balance, a safety filter, a transport
failure, or an empty result) the tool invocation fails instead of returning an error text, so
workflow retry and error branches can handle it. The error message carries the MiniMax
`base_resp` text where one is available; the plugin logs hold the request details.

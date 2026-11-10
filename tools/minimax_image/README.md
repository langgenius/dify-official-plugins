# MiniMax Image

Generate and edit images with [MiniMax-H3-Image](https://platform.minimax.io).

## Setup

1. Create an API key at [MiniMax International](https://platform.minimax.io) or [MiniMax China](https://platform.minimaxi.com). The two sites use separate accounts.
2. In Dify, install this plugin and open **Tools → MiniMax Image → Authorize**.
3. Paste the API key and select the matching endpoint (`api.minimax.io` or `api.minimaxi.com`).

## Tools

- **Image Generate**: text-to-image. Optional aspect ratio (`1:1`, `16:9`, `9:16`, `4:3`, `3:4`), area (`1K` / `2K` / `4K`), and count (`n`, 1–10).
- **Image Edit**: edit 1–16 reference images with a prompt. The same aspect ratio and area options are available.

A single request can take up to 600 seconds. The API is not idempotent, so failed or timed-out requests should not be retried automatically.

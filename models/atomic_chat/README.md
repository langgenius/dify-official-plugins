# Atomic Chat model provider for Dify

[Atomic Chat](https://atomic.chat) is a local-first desktop app for running open-weight LLMs with an OpenAI-compatible API at `http://127.0.0.1:1337/v1`.

## Quick start

1. Install [Atomic Chat](https://atomic.chat) and download at least one model.
2. Enable **Settings → Local API Server** (default port `1337`).
3. In Dify, install this plugin from the marketplace (or upload the `.difypkg`).
4. Open **Settings → Model Providers → Atomic Chat** and add a model:
   - **Model name**: the model id shown in Atomic Chat
   - **API endpoint URL**: `http://127.0.0.1:1337/v1`
   - **API key**: leave empty for a default local install

## Notes

- Dify runs in Docker by default. Use `http://host.docker.internal:1337/v1` on Docker Desktop (macOS/Windows), or your host LAN IP on Linux.
- Atomic Chat also supports MCP tools (web search, file access) inside the Atomic Chat app itself. This plugin connects Dify workflows to Atomic Chat as the LLM backend.

## Links

- [Atomic Chat](https://atomic.chat)
- [GitHub](https://github.com/AtomicBot-ai/Atomic-Chat)

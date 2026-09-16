# OpenCode Go 0.1.0 — session isolation via extra_headers

## Summary

Fixes sticky / collapsed `x-opencode-session` for Dify traffic and makes Chatflow / Workflow / Agent sessions isolate correctly.

Dify host does **not** pass `conversation_id` / `workflow_run_id` into the plugin `Session` (`PluginModelClient.invoke_llm` only sends `user_id`, `data`, optional `app_id`). Previous versions fell back to a sticky Dify user id, which collapsed every run onto one OpenCode console session.

This change:

1. Exposes an `extra_headers` model parameter (required, default JSON) so Dify resolves `{{#sys.conversation_id#}}` / `{{#sys.workflow_run_id#}}` before invoke.
2. Internally consumes helper header `x-dify-run-id` (never sent upstream) so Workflow LLM nodes in one run share a session when conversation is empty.
3. Rejects unresolved Dify templates (`{{#sys.*#}}`, `sys.`, empty, `null`) so they are never sent as session values.
4. Removes sticky-user fallback. Fallback chain is now: credential `session_id` → valid node session → valid run id → plugin Session conversation → RPC session id → random UUID.
5. Strips auto-persisted `dify-opencode-go/...` sessions from credentials on every invoke.
6. Sends bare unique IDs (no `dify-opencode-go/<client>/` prefix) per OpenCode docs.
7. Bumps version to **0.1.0** and updates User-Agent default to `dify-opencode-go-plugin/0.1.0`.

## Behavior matrix

| App type | extra_headers enabled | Session used |
| --- | --- | --- |
| Chatflow / chat | yes (default) | `conversation_id` |
| Workflow | yes (default) | `workflow_run_id` (shared by LLM nodes in one run) |
| Agent | any | per-invoke (RPC session or random) — intentionally not sticky |
| 0.0.2 upgrade (no extra_headers) | no | per-invoke isolation (never sticky user) |

## Catalog updates

- Vision / document / video / audio features refreshed on several predefined models (GLM, MiMo, MiniMax, etc.).
- Context size / max_tokens raised to match current OpenCode Go catalog where applicable.

## Tests

Local unit tests (no network), all passing:

- `test_session_id.py`
- `test_session_runtime.py`
- `test_extra_headers.py`
- `test_backward_compat_002.py`

Package verified: `dify plugin package models/opencode-go -o dist/opencode_go-0.1.0.difypkg`.

## Checklist

- [x] Version `0.1.0` in `manifest.yaml` / `pyproject.toml` / User-Agent
- [x] No secrets in tree (`.env` gitignored; `.env.example` placeholder only)
- [x] `debug_remote.py` / tests excluded from `.difypkg` via `.difyignore`
- [x] Unresolved `{{#sys.*#}}` never sent as `x-opencode-session`
- [x] No sticky Dify-user session fallback
- [x] Helper header `x-dify-run-id` stripped before upstream call
- [x] Upgrade path: nodes without `extra_headers` still work (per-invoke isolation)

## Related

- OpenCode docs: stable `x-opencode-session` per conversation for routing / prompt cache
- Prior plugin fix: #3891
- Dify host gap: plugin Session does not receive `conversation_id` / `workflow_run_id`

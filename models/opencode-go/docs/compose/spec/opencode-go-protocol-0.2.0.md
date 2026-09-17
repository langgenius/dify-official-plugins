---
feature: opencode-go-protocol-0.2.0
status: delivered
updated: 2026-09-17
branch: feat/opencode-go-protocol-0.2.0
commits: 13d6d563..c8e20e27 + live-debug fixes (pending)
---

# OpenCode Go 全协议适配 0.2.0

## Report

**What was built** — OpenCode Go 0.2.0 在单一供应商内支持三类上游协议：Chat Completions（默认）、Anthropic Messages（`union-alpha`）、OpenAI Responses（`grok-4.6` / `gpt-5.6-luna` / `muse-spark-*`）。因 dify_plugin 每个 ModelType 只保留一个 LLM 实现类，架构改为单入口路由，而非三个 model_sources。共用 `session_headers.py`，三条线均强制 UA + `x-opencode-session`，Anthropic 使用 `x-api-key` 且不发送 Authorization。自定义模型可通过 `api_protocol` 选择协议。0.1.0 会话隔离行为保持不变。

**Verification** — 单测：`test_session_id` / `test_session_runtime` / `test_extra_headers` / `test_backward_compat_002` / `test_protocol_routing`（26 项，含 SSE fixture / UTF-8 / 参数覆盖与剥离 / union-alpha 非流式仿真）全绿。实测：全部 chat 线模型 OK；`union-alpha` `/messages` OK（限时，流式易 503，已强制非流式仿真）；`minimax-m2.7` 仅 `/messages` 可用；`grok-4.6` / `gpt-5.6-luna` / `muse-spark-1.3` 经代理 `/responses` OK；12 个 vision 模型用户侧 Dify 实测通过。打包 `dist/opencode_go-0.2.0.difypkg` 成功。

**Journey log** — 1) 三 model_sources 被 SDK last-wins 语义否决，改为单入口路由。2) Windows + dify_plugin gevent ssl monkeypatch 会导致 requests 递归；冒烟脚本需先 import dify_plugin 并清代理。3) Anthropic SSE `message_delta` 与 `message_stop` 双 finish，需只在 message_stop 发 stop 且 usage 先于 stop。4) 连续同 role 消息与空 text block 会让 Messages 400，需规范化。5) 多轮审查后补齐 stop 参数映射与 SSE 回归测试。6) 实测：kimi-k2.7-code 仅允许 temperature=1/top_p=0.95（参数覆盖）；gpt-5.6-luna 拒绝 temperature/top_p（参数剥离）且需代理；union-alpha 流式易空/503，强制非流式仿真并从 message_delta 取 usage；SSE 需强制 UTF-8；瞬时 502/503/529 重试且 `trust_env=True` 走系统代理。

## [S1] Problem

0.1.0 仅走 OpenAI-compatible `/chat/completions`（OAICompat）。OpenCode Go 上部分模型不可用该路径：

- `union-alpha`：仅 Anthropic Messages `/messages` + `x-api-key`，oa-compat 实测 500
- `grok-4.6` / `gpt-5.6-luna` / `muse-spark-*`：仅 OpenAI Responses `/responses`

同一供应商需同时覆盖三条协议，且不回归 0.1.0 会话隔离。

## [S2] Design

### 架构修正（相对 PROTOCOL_ADAPTER_PLAN）

dify_plugin 0.10.2 `PluginRegistration._resolve_model_providers` 按 `ModelType` 注册：

```python
models[model_cls.model_type] = model_cls  # last wins
```

**不能**注册三个 `LargeLanguageModel` model_sources。采用**单入口路由**：

| 文件 | 角色 |
|---|---|
| `models/llm/llm.py` | 唯一 `LargeLanguageModel` 子类，`_invoke`/`validate_credentials`/`get_customizable_model_schema` 按协议分发 |
| `models/llm/session_headers.py` | 共用 session / UA / extra_headers 逻辑（从 llm.py 抽出） |
| `models/llm/llm_anthropic.py` | Anthropic Messages 协议实现（非 AIModel，纯适配器） |
| `models/llm/llm_responses.py` | OpenAI Responses 协议实现（非 AIModel，纯适配器） |

`provider/opencode_go.yaml` 仍只注册 `models/llm/llm.py`。

### 协议路由

优先级：

1. `credentials["api_protocol"]`（自定义模型）
2. 预置 model id 白名单：
   - `ANTHROPIC_MODELS = {"union-alpha", "minimax-m2.7"}`（m2.7 chat 500，仅 `/messages` 可用）
   - `RESPONSES_MODELS = {"grok-4.6", "gpt-5.6-luna", "muse-spark-1.3-contributor", "muse-spark-1.2-contributor"}`
3. 默认 `chat`

### 认证矩阵

| protocol | 端点 | 认证 | Session | UA |
|---|---|---|---|---|
| chat | `{base}/chat/completions` | `Authorization: Bearer` | 必须 | 必须 |
| anthropic | `{base}/messages` | `x-api-key` + `anthropic-version: 2023-06-01`（**不发** Authorization） | 必须 | 必须 |
| responses | `{base}/responses` | `Authorization: Bearer` | 必须 | 必须 |

Base URL 默认 `https://opencode.ai/zen/go/v1`。

### session_headers 契约

从 `llm.py` 抽出，三线复用：

- `DEFAULT_ENDPOINT_URL` / `DEFAULT_USER_AGENT`（0.2.0）
- `_RUN_ID_HEADER` / `_is_resolved_id` / `_parse_extra_headers` / `_apply_extra_headers`
- `_add_custom_parameters` / `_build_session_id` / `_current_conversation_id` / `_current_rpc_session_id`
- `_extra_headers_rule`

约束保持 0.1.0：不发送 `x-dify-run-id`、不发送未解析模板、不做 sticky user。

### Anthropic 线（优先交付）

`POST {base}/messages`：

- body：`model`, `messages`（user/assistant，tool_result 折进 user）, `system`, `max_tokens` 必填, 可选 `temperature`/`top_p`/`stop_sequences`/`stream`/`tools`
- 认证头：`x-api-key`, `anthropic-version: 2023-06-01`
- 非流式：`content[].text` → `AssistantPromptMessage`；`usage.input_tokens/output_tokens`
- 流式 SSE：`message_start` / `content_block_delta` / `content_block_stop` / `message_delta` / `message_stop` / `ping` / `error`
- tool：Dify `PromptMessageTool` → Anthropic `tools[]`；`tool_use` / `tool_result` 映射
- validate：`max_tokens=8` ping；错误映射到 Dify Invoke*Error

### Responses 线

`POST {base}/responses`：

- body：`model`, `input`（字符串或 item 列表）, `max_output_tokens`, `temperature`, `top_p`, `stream`, `tools`
- 非流式：聚合 `output[].content[].text`；`usage.input_tokens/output_tokens`
- 流式 SSE：`response.created` / `response.output_text.delta` / `response.completed` / `response.failed` / `error`
- validate：小 max_output_tokens ping
- 注入 UA + session + Bearer

### 预置模型增量

| model id | label | protocol | 策略 |
|---|---|---|---|
| union-alpha | Union Alpha Free (Limited) | anthropic | limited-time 标注 |
| grok-4.6 | Grok 4.6 | responses | 预置 |
| gpt-5.6-luna | GPT 5.6 Luna | responses | 预置 |
| muse-spark-1.3-contributor | Muse Spark 1.3 Contributor | responses | 预置 + 区域限制说明 |
| muse-spark-1.2-contributor | Muse Spark 1.2 Contributor | responses | 同上 |

**不迁移** qwen/minimax（oa-compat 实测 200）。

context_size / max_tokens / features / pricing：以 OpenCode 文档与 `/models` API 为准；文档未给出的用保守值并在 README 说明。

### 版本

0.2.0：manifest、pyproject、DEFAULT_USER_AGENT、provider user_agent 默认值。

## [S3] Out of Scope

- 不改 Dify 宿主
- 不做 Muse 区域限制产品化（能通则通，不通给清晰错误）
- 不实现 Anthropic 高级特性（prompt cache / adaptive thinking / task_budget）
- 不把 models API 有但文档未承诺的 ID 做进预置

## Tasks

- [x] T1: 抽取 `session_headers.py`，`llm.py` 改为 import — acceptance: 既有 4 套单测全绿 (covers: S2)
- [x] T2: Anthropic Messages 适配器 + `union-alpha` 预置 + 路由 — acceptance: union-alpha `/messages` 实测 200（stream + non-stream）(covers: S2; depends: T1)
- [x] T3: Responses 适配器 + grok/gpt/muse 预置 + 路由 — acceptance: grok-4.6 或 gpt-5.6-luna 实测 200 (covers: S2; depends: T1)
- [x] T4: provider yaml `api_protocol` + schema 注入三线 — acceptance: 自定义模型可按协议校验 (covers: S2; depends: T2, T3)
- [x] T5: README 中英协议矩阵 + 版本 0.2.0 + `.difyignore` — acceptance: 文档与版本一致 (covers: S2)
- [x] T6: 单测（无网）+ 冒烟矩阵 + 打包 difypkg — acceptance: 单测全绿；既有模型不回归；包可生成 (covers: S2; depends: T2, T3, T4, T5)
- [x] T7: 多轮代码审查 + 模型元数据核对 — acceptance: 无 critical；元数据与文档/API 一致 (covers: S2; depends: T6)

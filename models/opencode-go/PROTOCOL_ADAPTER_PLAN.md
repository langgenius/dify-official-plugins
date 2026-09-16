# OpenCode Go 全协议适配方案（0.2.0）

> 交接文档：供新会话以 compose-next（编排模式）实施。
> 基线：`feat/opencode-go-session-isolation-0.1.0`（会话隔离已合入待 PR）。
> 仓库：`D:\Mimo-workspace\dify-official-plugins`，插件目录 `models/opencode-go/`。

## 1. 目标

在 **同一 OpenCode Go 供应商**内完整支持三类上游协议，做到：

1. 预置模型目录与 OpenCode Go 文档/API 对齐，且 **oa-compat 能通的走 OAICompat**。
2. 仅 Anthropic Messages 可用的模型（如 `union-alpha`）走 `/messages`。
3. 仅 OpenAI Responses 可用的模型（`grok-4.6`、`gpt-5.6-luna`、`muse-spark-*`）走 `/responses`。
4. 三条线共用：Base URL、User-Agent、`x-opencode-session` 会话隔离、extra_headers、凭证。
5. 不回归 0.1.0 已交付的 Chatflow/Workflow session 行为。

**非目标（本阶段不做）**

- 不改 Dify 宿主。
- 不把 Muse 区域限制做成产品能力（能通则通，不通给清晰错误）。
- 不实现 Anthropic 全量高级特性（prompt cache / adaptive thinking / task_budget），只做 OpenCode 网关实际接受的子集。

## 2. 现状与实测结论

| 模型 | 文档端点 | `/chat/completions` 实测 | 可用路径 |
|---|---|---|---|
| glm/kimi/deepseek/mimo/hy/longcat | `/chat/completions` | 200 | OAICompat |
| qwen3.* / minimax-m* | `/messages` | 200 | **继续 OAICompat**（已验证） |
| `union-alpha` | `/messages` | **500** | 仅 Anthropic Messages |
| grok-4.6 / gpt-5.6-luna | `/responses` | 未测，文档拒绝 oa-compat | OpenAI Responses |
| muse-spark-* | `/responses` | 区域限制 | OpenAI Responses（可选） |

`union-alpha` Messages 实测要点：

- URL：`POST https://opencode.ai/zen/go/v1/messages`
- 认证：`x-api-key: <key>`（**不是** `Authorization: Bearer`）
- 必带：`User-Agent: dify-opencode-go-plugin/<ver>`、`x-opencode-session: <stable-id>`
- 缺 session → 400 `MissingSessionID`
- 无 UA / 错误认证头 → Cloudflare 1010 或 401
- 成功响应为 Anthropic Message JSON（`content[].text`，`stop_reason: end_turn`）

## 3. 架构

### 3.1 三个模型类，一个 Provider

```
models/opencode-go/
  models/llm/llm.py              # 现有 OAICompatLargeLanguageModel（chat/completions）
  models/llm/llm_anthropic.py    # 新增：Anthropic Messages（/messages）
  models/llm/llm_responses.py    # 新增：OpenAI Responses（/responses）
  models/llm/session_headers.py # 抽出：session / UA / extra_headers 共用逻辑
  models/llm/_position.yaml
  models/llm/<model>.yaml        # 预置模型，带 protocol 归属
  provider/opencode_go.yaml      # model_sources 注册三个实现
```

`provider/opencode_go.yaml`：

```yaml
extra:
  python:
    model_sources:
      - models/llm/llm.py
      - models/llm/llm_anthropic.py
      - models/llm/llm_responses.py
    provider_source: provider/opencode_go.py
```

### 3.2 协议路由策略（两层）

**层 1：预置模型静态绑定（推荐主路径）**

在预置 YAML 中用 Dify 支持的模型实现绑定（若宿主版本支持 per-model source 指定则用之；否则按 model id 白名单在各类中处理）。

实现上更稳妥的做法：**每个实现类只处理自己的 model id 集合**，provider 通过 `get_model_instance` / 自定义 factory 路由。若 SDK 无法 per-model 指定 class，则：

- `llm.py` 保留全部现有预置 + qwen/minimax（oa-compat 可用）。
- `llm_anthropic.py` 仅注册 `union-alpha` 及未来仅 Messages 模型。
- `llm_responses.py` 仅注册 grok / gpt-luna / muse-spark。

**层 2：自定义模型协议选择**

`model_credential_schema` / provider 增加可选字段：

```yaml
- variable: api_protocol
  type: select
  required: false
  default: chat
  options:
    - value: chat        # /chat/completions + Bearer
    - value: anthropic   # /messages + x-api-key
    - value: responses   # /responses + Bearer
```

自定义模型按 `api_protocol` 走对应实现；默认 `chat` 保持 0.1.0 行为。

### 3.3 共用模块 `session_headers.py`

从 `llm.py` 抽出，供三类调用：

- `DEFAULT_ENDPOINT_URL`、`DEFAULT_USER_AGENT`
- `_RUN_ID_HEADER`、`_is_resolved_id`、`_parse_extra_headers`
- `_apply_extra_headers`、`_add_custom_parameters`、`_build_session_id`
- `_current_conversation_id`、`_current_rpc_session_id`

**约束：**

1. 三条线最终都必须设置 `extra_headers["x-opencode-session"]`。
2. `x-dify-run-id` 仍只本地消费，永不外发。
3. 未解析 `{{#sys.*#}}` 永不作为 session。
4. 不做 sticky user。
5. Anthropic 线额外写 `x-api-key`（来自 `credentials["api_key"]`），并 **删除/不发送** `Authorization`（避免 401）。
6. Responses / chat 线继续 `Authorization: Bearer`。

### 3.4 认证矩阵

| protocol | 端点 | 认证头 | Session | UA |
|---|---|---|---|---|
| chat | `{base}/chat/completions` | `Authorization: Bearer` | 必须 | 必须 |
| anthropic | `{base}/messages` | `x-api-key` + `anthropic-version: 2023-06-01` | 必须 | 必须 |
| responses | `{base}/responses` | `Authorization: Bearer` | 必须 | 必须 |

Base URL 均为 `https://opencode.ai/zen/go/v1`。

## 4. 模型目录策略

### 4.1 原则

1. **能 oa-compat 的一律 oa-compat**（qwen/minimax 不要迁到 anthropic，避免无谓回归）。
2. 仅文档且实测 **明确不可** oa-compat 的进 anthropic/responses 预置。
3. 限时模型（`union-alpha`）进预置时 README/label 标注 `limited time`。
4. `grok-4.6` / `gpt-5.6-luna` 进 responses 预置；`muse-spark-*` 可进但 README 注明区域限制。

### 4.2 0.2.0 预置增量

| model id | label | protocol | features 初值 |
|---|---|---|---|
| union-alpha | Union Alpha Free (Limited) | anthropic | agent-thought, tool-call?, stream-tool-call?（以实测为准） |
| grok-4.6 | Grok 4.6 | responses | agent-thought, tool-call, stream-tool-call |
| gpt-5.6-luna | GPT 5.6 Luna | responses | agent-thought, tool-call, stream-tool-call |
| muse-spark-1.3-contributor | Muse Spark 1.3 Contributor | responses | agent-thought（区域限制说明） |
| muse-spark-1.2-contributor | Muse Spark 1.2 Contributor | responses | 同上 |

context_size / max_tokens / pricing 按 OpenCode 文档表填；文档未给的用保守默认并在 help 说明。

### 4.3 不预置

- `omen-alpha`、`kimi-k2.5`、`glm-5`、`deepseek-flash`、`qwen3.5-plus`、`mimo-v2-pro`、`mimo-v2-omni`、`hy3-preview`、`grok-4.5` 等 models API 有但文档未承诺的 ID：先不进预置，用户可自定义 + `api_protocol`。

## 5. 实现拆解（compose-next 任务）

### T1 抽取共用 session 模块

- 从 `llm.py` 抽出 `session_headers.py`，`llm.py` 改为 import。
- 行为不变；现有 4 套单测全绿。

### T2 Anthropic Messages 实现

文件：`models/llm/llm_anthropic.py`

建议基类：继承 `LargeLanguageModel`，请求用 `httpx`/`requests` 直打 `/messages`（**不要**强绑 anthropic SDK 默认 base，除非验证 `base_url` + `x-api-key` 可控）。

必做：

1. `_invoke`：组装 Anthropic Messages body  
   - `model`, `messages`, `max_tokens`（必填）, 可选 `temperature`/`top_p`/`stop_sequences`  
   - system 单独字段（从 SystemPromptMessage 抽出）
2. 非流式解析：`content[].text` → `LLMResult`；`usage.input_tokens/output_tokens`
3. 流式：解析 Anthropic SSE（`message_start` / `content_block_delta` / `message_delta` / `message_stop`）→ `LLMResultChunk`
4. Tool call（第二优先级）：`tools` → Anthropic `tools[]`；`tool_use` / `tool_result` 双向映射
5. `validate_credentials`：用目标模型发 `max_tokens=8` 的 ping；500/400 给可读错误（区分“无 oa-compat”与“鉴权失败”）
6. 错误映射到 `InvokeAuthorizationError` / `InvokeBadRequestError` / `InvokeRateLimitError` / `InvokeServerUnavailableError`
7. 调用 `session_headers` 注入 UA + session；认证用 `x-api-key`

预置：`union-alpha.yaml` + `_position.yaml` 更新。

### T3 OpenAI Responses 实现

文件：`models/llm/llm_responses.py`

1. `POST {base}/responses`  
   body 参考 OpenAI Responses：`model`, `input`（或 messages 形态按网关实测）, `max_output_tokens` / `temperature` 等
2. 非流式：从 `output` items 聚合 text；usage 映射
3. 流式：Responses SSE 事件（`response.output_text.delta` 等，以实测为准）
4. Tool call：Responses tool 定义与 `function_call` item 映射（可放第二批）
5. `validate_credentials` + 明确错误文案
6. 注入 UA + session + Bearer

预置：grok-4.6 / gpt-5.6-luna /（可选）muse-spark。

### T4 Provider / Schema

1. `provider/opencode_go.yaml`：注册三个 `model_sources`；`model_credential_schema` 增加 `api_protocol`。
2. `provider/opencode_go.py`：provider 级校验仍用 `glm-5.3-flash`（chat）。
3. 自定义模型：按 `api_protocol` 选择实现类校验。
4. `extra_headers` 参数规则继续注入到三类模型（复用 `_extra_headers_rule`）。

### T5 目录与文档

1. 新预置 yaml + `_position.yaml`
2. README / README_zh_Hans：协议矩阵表、union-alpha limited-time、muse 区域限制、自定义 `api_protocol` 说明
3. 版本 **0.2.0**（manifest / pyproject / User-Agent / provider default）
4. `.difyignore` 保持排除测试与 debug 文件

### T6 测试与打包

**单元（无网）**

- session 复用：anthropic/responses 路径也生成稳定 session、剥 `x-dify-run-id`
- 协议路由：`api_protocol` 选择正确实现
- 消息转换：Dify PromptMessage → Anthropic body / Responses body
- 流式解析：用录制的 SSE fixture

**实测冒烟（需 `OPENCODE_GO_API_KEY`）**

| 模型 | chat | anthropic | responses |
|---|---|---|---|
| glm-5.3-flash | 必须 200 | — | — |
| qwen3.8-flash | 必须 200 | — | — |
| minimax-m3 | 必须 200 | — | — |
| union-alpha | 500（预期） | **必须 200** | — |
| grok-4.6 | 预期失败 | — | **目标 200** |
| gpt-5.6-luna | 预期失败 | — | **目标 200** |

另测：stream / non-stream / tool-call（能通的模型）/ validate_credentials。

**打包**

```text
dify plugin package models/opencode-go -o dist/opencode_go-0.2.0.difypkg
```

### T7 PR 策略

建议 **两个 PR**，避免 0.1.0 会话修复被大功能拖住：

1. **PR-A（可先发）**：0.1.0 会话隔离（当前分支已就绪）  
2. **PR-B**：0.2.0 全协议适配（本方案 T1–T6）

若必须单 PR：版本直接 0.2.0，PR 描述分两段写清。

## 6. 风险与对策

| 风险 | 对策 |
|---|---|
| OpenCode Messages 为 Anthropic 子集，SDK 全量参数 400 | 只发白名单参数；未知参数剥离 |
| Responses 入参形态与 OpenAI 官方不完全一致 | 先 curl 录真实请求/响应，再写转换；fixture 驱动开发 |
| 流式事件类型差异 | 每协议单独 SSE 解析；失败降级提示“请用非流式” |
| Cloudflare 1010 | 三线都强制非空 User-Agent |
| 多实现类 + Dify 宿主路由不清晰 | 先写最小 spike：anthropic 类只注册 union-alpha，验证 invoke 路由 |
| tool call 复杂度 | 分两批：先 text 通，再 tool；PR-B1 text-only 也可合 |
| 限时模型下线 | label + README 标注；不阻塞其它模型 |

## 7. 验收标准

1. 预置目录中每个模型在 Dify 中可选，且调用成功（区域/限时除外并有明确错误）。
2. Chatflow 同对话 session 稳定；Workflow 同 run 共享 session——**三协议均成立**。
3. 不发送未解析模板、不发送 `x-dify-run-id`、不 sticky user。
4. 自定义模型可用 `api_protocol` 切换三协议。
5. 单元测试全绿；实测矩阵通过；0.2.0 包可安装。
6. README 中英文一致。

## 8. 新会话开工指令（建议原样粘贴）

```text
请使用 /compose-next 编排模式实施 models/opencode-go 全协议适配。
完整方案见：models/opencode-go/PROTOCOL_ADAPTER_PLAN.md
基线分支：feat/opencode-go-session-isolation-0.1.0（会话隔离已完成，勿回退）。
要求：
1. 先读该 PLAN 与 models/opencode-go/models/llm/llm.py
2. 按 T1→T2→T4→T5→T6 做 Anthropic 线并实测 union-alpha
3. 再 T3 做 Responses 线（grok-4.6 / gpt-5.6-luna）
4. 版本 0.2.0；共用 session_headers.py；qwen/minimax 保持 OAICompat
5. 完成后打包 dist/opencode_go-0.2.0.difypkg，并给出实测矩阵
工作区：D:\Mimo-workspace\dify-official-plugins
Python：D:\Mimo-workspace\opencode-go\.venv\Scripts\python.exe
dify CLI：D:\Development\dify-plugin\dify.exe
OPENCODE_GO_API_KEY：运行前向用户要，勿写入仓库
```

## 9. 本会话已确认事实（供新会话复用）

- 0.1.0 会话隔离逻辑与测试已就绪；分支 `feat/opencode-go-session-isolation-0.1.0`，提交 `13d6d563`。
- `union-alpha` 仅 `/messages` + `x-api-key` + session 可通；oa-compat 500。
- qwen/minimax 虽文档 `/messages`，oa-compat 实测 200，**不要**迁移。
- grok/gpt/muse 走 Responses；本方案默认纳入 grok 与 gpt-luna，muse 可选。
- Dify 自定义模型不会继承供应商 API Key（两级凭证，属宿主设计）。
- 打包命令与 `.difyignore` 约定见 T5/T6。

# OpenCode Go

[Dify](https://dify.ai) 的 [OpenCode Go](https://opencode.ai/docs/go/) 模型供应商插件。

OpenCode Go 是 $10/月 的订阅网关，提供精选开源编码模型。本插件通过 OpenAI 兼容的 Chat Completions API 将这些模型接入 Dify。

## 功能

- 预置 OpenCode Go 目录中的模型（GLM、Kimi、DeepSeek、MiMo、MiniMax、Qwen、LongCat、Hy、Grok、GPT 5.6 Luna、Muse Spark）
- 支持自定义模型，便于接入官方新增的 model id
- 自动发送 OpenCode 要求的请求头：
  - `User-Agent`（标识客户端）
  - `x-opencode-session`（会话路由 / prompt cache）
- 默认 Base URL：`https://opencode.ai/zen/go/v1`

## 使用步骤

1. 在 [opencode.ai/auth](https://opencode.ai/auth) 订阅 OpenCode Go 并复制 API Key。
2. 在 Dify 中安装本插件（市场 / 本地包 / 远程调试）。
3. 打开 **设置 → 模型供应商 → OpenCode Go**，粘贴 API Key 并保存。
4. 在应用中选择 OpenCode Go 模型。

### 自定义模型

若 OpenCode 新增模型而插件尚未收录：

1. 在 OpenCode Go 下添加自定义模型。
2. 模型名称填写 [Go 文档](https://opencode.ai/docs/go/) 中的 model id（例如 `kimi-k2.6`）。
3. 可按需设置上下文长度、最大 token、Function Calling、视觉能力。

## 协议说明

OpenCode Go 对不同模型暴露了不同的 AI SDK 路径：

| 端点路径 | 模型 |
| --- | --- |
| `/chat/completions` | GLM、Kimi、LongCat、DeepSeek、MiMo、Hy |
| `/messages`（Anthropic 风格） | MiniMax、Qwen |
| `/responses`（OpenAI Responses） | Grok 4.6、GPT 5.6 Luna、Muse Spark |

本插件默认走 **OpenAI 兼容** 路径（`{base}/chat/completions`），与 Cline / Claude Code 等客户端一致，覆盖大部分 Go 模型。若个别仅支持 Responses 或 Anthropic 协议的模型失败，可先用自定义模型或提 Issue。

## 本地调试

```bash
pip install "dify_plugin>=0.10.0"
```

复制 `.env.example` 为 `.env`，填入 Dify 插件调试页中的密钥。

```bash
python -m main
```

打包：

```bash
dify plugin package .
```

## 相关链接

- OpenCode Go 文档：https://opencode.ai/docs/go/
- 模型列表 API：`https://opencode.ai/zen/go/v1/models`
- API Key：https://opencode.ai/auth
- Dify 插件开发文档：https://docs.dify.ai/zh/develop-plugin/dev-guides-and-walkthroughs/creating-new-model-provider

## 免责声明

本插件为社区非官方实现，与 OpenCode / Anomaly 及 Dify 无官方关联。

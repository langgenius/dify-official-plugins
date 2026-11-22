# bf16.ai Dify 模型插件

[bf16.ai](https://bf16.ai) 的 Dify 官方模型插件，通过 OpenAI 兼容协议提供 1M 上下文免审查开源权重模型推理，默认严格零数据留存（ZDR），支持按量付费。

## 支持模型

| 模型 ID | 上下文窗口 | 最大输出 | 模态 | 核心能力 |
| --- | --- | --- | --- | --- |
| `zai-org/glm-5.3-uncensored` | 1M | 131,072 | 文本 | 工具调用、结构化输出、推理 |
| `deepseek/deepseek-v4.1-flash-uncensored` | 1M | 130,000 | 文本 + 视觉 | 工具调用、结构化输出、推理 |
| `deepseek/deepseek-v4.1-flash-uncensored-fast` | 1M | 130,000 | 文本 + 视觉 | 工具调用、结构化输出、推理 |
| `zai-org/glm-5.3-flash-uncensored` | 1M | 131,072 | 文本 + 视觉 | 工具调用、结构化输出、推理 |
| `moonshotai/kimi-k3.1-pro-uncensored` | 1M | 131,072 | 文本 + 视觉 | 工具调用、结构化输出、推理 |

## 配置方式

1. 在 [bf16.ai 开发者控制台](https://bf16.ai/dashboard/keys) 创建 API Key。
2. 在 Dify 中打开 **设置 -> 模型供应商 -> bf16.ai**。
3. 填入你的 `sk-bf16-v1-...` API Key（可选填写自定义 API Base URL，默认 `https://api.bf16.ai/v1`）。

## 文档与定价格表

- 接口文档：https://bf16.ai/docs
- 实时定价与速率档位：https://bf16.ai/pricing

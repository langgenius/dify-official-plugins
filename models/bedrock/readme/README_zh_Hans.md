## Amazon Bedrock

**Author:** aws
**Type:** Model Provider



## Overview | 概述

The [Amazon Bedrock](https://aws.amazon.com/bedrock/) is a fully managed service that offers a choice of high-performing foundation models (FMs) from leading AI companies like AI21 Labs, Anthropic, Cohere, Meta, Stability AI, and Amazon with a single API. With Amazon Bedrock, you can easily experiment with and evaluate top FMs for your use case, privately customize them with your data using techniques such as Retrieval Augmented Generation (RAG) and Fine-tuning, and build agents that execute tasks using your enterprise systems and data sources.

Amazon Bedrock supports various model types:
- LLM (Large Language Models)
- Text Embedding
- Rerank

[Amazon Bedrock](https://aws.amazon.com/bedrock/) 是一项完全托管的服务，通过单一 API 提供来自 AI21 Labs、Anthropic、Cohere、Meta、Stability AI 和亚马逊等领先 AI 公司的高性能基础模型 (FMs)。使用 Amazon Bedrock，您可以轻松地为您的用例试验和评估顶级基础模型，使用检索增强生成 (RAG) 和微调等技术私密地用您的数据进行定制，并构建能够使用您的企业系统和数据源执行任务的代理。

Amazon Bedrock 支持多种模型类型：
- LLM（大型语言模型）
- 文本嵌入
- 重排序



## Configure | 配置

After installing the plugin, configure the Amazon Bedrock credentials within the Model Provider settings. You'll need to provide your AWS Access Key, Secret Access Key, and select the appropriate AWS Region. You can also specify a Bedrock Endpoint URL if needed. For validation purposes, you can provide an available model name that you have access to (e.g., amazon.titan-text-lite-v1).

安装插件后，在模型提供商设置中配置 Amazon Bedrock 凭证。您需要提供 AWS Access Key、Secret Access Key 并选择适当的 AWS 区域。如果需要，您还可以指定 Bedrock 端点 URL。为了进行验证，您可以提供一个您有权访问的可用模型名称（例如：amazon.titan-text-lite-v1）。

![](../_assets/configure.png)



## Claude 5 系列模型（Sonnet 5 / Fable 5）

“Anthropic Claude 5” 条目提供 Claude Sonnet 5（`anthropic.claude-sonnet-5`）与 Claude Fable 5（`anthropic.claude-fable-5`）。与之前的 Claude 世代相比：

- **仅支持推理配置文件调用。** 只能通过 `us.`（美国/加拿大区域）或 `global.` 跨区域推理配置文件调用——不支持裸模型 ID 的按需调用，也没有 `eu.`/`apac.` 地理配置文件。插件根据“跨区域推理”选项自动解析；非美国区域请选择 `global`。
- **自适应思考始终开启**，无法关闭。思考深度由 Effort 参数（`low`/`medium`/`high`/`xhigh`/`max`）控制，取代思考预算。这两个模型不支持调节采样参数（temperature / top_p / top_k），因此不再暴露。
- **拒答与回落。** 请求可能被安全分类器拒绝（`stop_reason: refusal`，Fable 5 概率明显更高）。默认开启“拒答回落”时，插件会自动用 Claude 4.8 Opus 重试同一请求；流式输出已产生内容后发生的拒绝无法回落，将直接报错。
- **Fable 5 前置条件：数据保留 opt-in。** 调用 Fable 5 前，AWS 账户必须通过 Bedrock Data Retention API 将数据保留模式设置为 `provider_data_share`（上线初期无控制台入口）。详见 [Fable 5 模型卡](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-fable-5.html)。插件不会修改账户设置。
- **价格说明。** 展示价格为 Global 跨区域费率（Sonnet 5 每百万 token $3/$15，Fable 5 $10/$50）。Geo/区域内调用约贵 10%。Prompt 缓存读写费率无法体现在 Dify 费用统计中，请以 AWS 账单为准。

## Issue Feedback | 问题反馈

For more detailed information, please refer to [aws-sample/dify-aws-tool](https://github.com/aws-samples/dify-aws-tool/), which contains multiple workflows for reference.

更多详细信息可以参考 [aws-sample/dify-aws-tool](https://github.com/aws-samples/dify-aws-tool/)，其中包含多个 workflow 供参考。

If you have issues that need feedback, feel free to raise questions or look for answers in the [Issue](https://github.com/aws-samples/dify-aws-tool/issues) section.

如果存在问题需要反馈，欢迎到 [Issue](https://github.com/aws-samples/dify-aws-tool/issues) 去提出问题或者寻找答案。

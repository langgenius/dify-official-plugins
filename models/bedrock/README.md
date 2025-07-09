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

安装插件后，在模型提供商设置中配置 Amazon Bedrock 凭证。您需要提供 AWS Access Key、Secret Access Key 并选择适当的 AWS 区域。如果需要，您还可以指定 Bedrock 端点 URL。为了进行验证，您可以提供一个您有权访问的可用模型名称（例如：mistral.mistral-7b-instruct-v0:2）。

![](./_assets/configure.png)

### 1. 获取 Access Key 与 Secret Access Key

1. 登录 AWS 控制台。

点击右上角的账户名，选择 **“安全凭证”**（Security Credentials）菜单项。
![](./_assets/Acess.png)
在页面中找到 **“访问密钥 (Access Key)”** 一栏，点击 **“创建访问密钥”**。
![](./_assets/Key.png)

1. 成功创建后，您将获得一组 `Access Key ID` 和 `Secret Access Key`。请妥善保存这两个值，它们是后续 API 调用所必需的身份凭证。

------

### 2. 查找对应 Region 的 Endpoint URL

根据您在 AWS 中选择的 Region（区域），需要配置相应的服务 Endpoint。请参考 AWS 官方文档：

🔗 [Amazon Bedrock endpoints and quotas - AWS General Reference](https://docs.aws.amazon.com/general/latest/gr/bedrock.html)

在此页面中，您可以找到每个 Region 对应的 Bedrock API 端点，例如：

- `us-east-1`: bedrock-runtime.us-east-1.amazonaws.com (Https协议)
- `eu-central-1`: bedrock-runtime.eu-central-1.amazonaws.com (Https协议)

请确保在代码或配置中使用与您资源所在区域一致的 Endpoint。

------

### 3. 确认模型名称与授权情况

Amazon Bedrock 支持多个基础模型（Foundation Models），您可以通过以下链接查阅当前支持的模型列表：

🔗 [Amazon Bedrock 中支持的根基模型 - Amazon Bedrock](https://docs.aws.amazon.com/zh_cn/bedrock/latest/userguide/models-supported.html)

在页面中，您可以查看以下信息：

- 模型名称（如 Claude, Titan, Jurassic 等）
- 模型提供商（如 Anthropic, AI21, Amazon 等）
- 模型 ID（用于 API 调用）
- 支持的功能（聊天、文本生成、图像生成等）

> ⚠️ **注意：**
>  使用某个模型前，您必须先在 AWS 控制台中启用该模型的访问权限。若该模型在您的账户中显示“已授权访问权限”，则说明您可以直接使用该模型，无需在代码中额外添加模型 ID 进行授权申请。


## Issue Feedback | 问题反馈

For more detailed information, please refer to [aws-sample/dify-aws-tool](https://github.com/aws-samples/dify-aws-tool/), which contains multiple workflows for reference.

更多详细信息可以参考 [aws-sample/dify-aws-tool](https://github.com/aws-samples/dify-aws-tool/)，其中包含多个 workflow 供参考。

If you have issues that need feedback, feel free to raise questions or look for answers in the [Issue](https://github.com/aws-samples/dify-aws-tool/issues) section.

如果存在问题需要反馈，欢迎到 [Issue](https://github.com/aws-samples/dify-aws-tool/issues) 去提出问题或者寻找答案。

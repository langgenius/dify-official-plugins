# 概述

- [配置](#配置)

Gemini 是 Google 推出的多模态 AI 模型系列,旨在处理和生成各种类型的数据,包括文本、图像、音频和视频。此插件通过单个 API 密钥提供对 Gemini 模型的访问,使开发者能够构建多功能的多模态 AI 应用程序。

## Gemini 4 Argon

使用付费 Gemini API 密钥，选择 `gemini-4-argon`。
支持文本、图片、音频、视频和 PDF 输入，以及文本输出、函数调用、结构化输出、Google 搜索、链接上下文和代码执行。
输入、思考与输出共用 1,048,576 tokens 的上下文窗口。
思考等级默认为 Medium，也可选择 Low 或 High。
输出上限默认为 65,536 tokens，提高上限会启用 Google GenAI SDK 的自动续写，最多使用剩余上下文窗口。
插件每次请求的超时为 15 分钟，长时间推理也需要 Dify 部署配置相应的超时。

截至 2026 年 11 月 30 日，Standard 优惠价格为每百万输入 tokens 2 美元、每百万输出 tokens 10 美元，输出包含思考 tokens。
Google 公布的价格自 2026 年 12 月 1 日起分别为 4 美元和 20 美元，届时需要更新插件的价格配置。
Google 支持该模型的隐式缓存，不支持显式上下文缓存。
详见[发布公告](https://blog.google/innovation-and-ai/technology/developers-tools/build-with-gemini-4-argon/)、[模型规格](https://ai.google.dev/gemini-api/docs/models/gemini-4-argon)、[长输出指南](https://ai.google.dev/gemini-api/docs/generate-content/long-decode)和[价格表](https://ai.google.dev/gemini-api/docs/pricing#gemini-4-argon)。

## 配置
安装 Gemini 插件后,使用您从 Google 获取的 API 密钥进行配置。在模型提供商设置中输入密钥并保存。

![](./_assets/gemini-01.png)

如果您在 Gemini 和其他视觉模型中同时对 `MULTIMODAL_SEND_FORMAT` 使用 `url` 模式,可以设置 `Files URL` 以获得更好的性能。

`Enable request metadata` 为可选项,默认禁用。启用后,会将 `dify_app_id` 和 `dify_source` 作为 `labels` 附加到 `GenerateContentConfig` 的每次 Gemini 请求中,以便在 Cloud Billing 中将用量归因到特定的 Dify 应用。此选项仅适用于 `generate_content` 路由;Interactions API 不会在其账单明细中显示 labels,因此有意不受影响。Dify 会话查找采用尽力而为的方式:如果会话上下文未初始化,则不会附加任何 labels,请求将保持不变发送。


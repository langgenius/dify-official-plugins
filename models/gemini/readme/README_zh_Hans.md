# 概述

- [配置](#配置)

Gemini 是 Google 推出的多模态 AI 模型系列,旨在处理和生成各种类型的数据,包括文本、图像、音频和视频。此插件通过单个 API 密钥提供对 Gemini 模型的访问,使开发者能够构建多功能的多模态 AI 应用程序。

## 配置
安装 Gemini 插件后,使用您从 Google 获取的 API 密钥进行配置。在模型提供商设置中输入密钥并保存。

![](./_assets/gemini-01.png)

如果您在 Gemini 和其他视觉模型中同时对 `MULTIMODAL_SEND_FORMAT` 使用 `url` 模式,可以设置 `Files URL` 以获得更好的性能。

`Enable request metadata` 为可选项,默认禁用。启用后,会将 `dify_app_id` 和 `dify_source` 作为 `labels` 附加到 `GenerateContentConfig` 的每次 Gemini 请求中,以便在 Cloud Billing 中将用量归因到特定的 Dify 应用。此选项仅适用于 `generate_content` 路由;Interactions API 不会在其账单明细中显示 labels,因此有意不受影响。Dify 会话查找采用尽力而为的方式:如果会话上下文未初始化,则不会附加任何 labels,请求将保持不变发送。


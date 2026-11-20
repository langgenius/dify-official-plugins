# 概述

- [配置](#配置)

Gemini 是 Google 推出的多模态 AI 模型系列,旨在处理和生成各种类型的数据,包括文本、图像、音频和视频。此插件通过单个 API 密钥提供对 Gemini 模型的访问,使开发者能够构建多功能的多模态 AI 应用程序。

## Gemini 4

Carbon、Neon、Hydrogen 和 Argon 支持文本、图像、音频、视频和 PDF 输入。
四个模型都支持文本输出、函数调用、结构化输出、Google 搜索、URL 上下文和代码执行。
Carbon、Neon 和 Argon 需要启用付费的 API 密钥。
输入、思考与输出共用 1,048,576 token 的上下文。
输出上限默认为 65,536，提高上限后 SDK 会在剩余上下文内自动续写。
单次 API 请求的超时为 15 分钟。

| 模型 | 默认思考等级 | 其他等级 | 每百万输入 / 输出 token 的标准价（美元） |
| --- | --- | --- | --- |
| Carbon、Argon | Medium | Low、High | 2026 年 11 月 30 日前（含当日）为 2 / 10，之后为 4 / 20 |
| Neon | High | Low、Medium、Xhigh | 3 / 15 |
| Hydrogen | High | Low、Medium、Xhigh | 1.50 / 7.50 |

隐式缓存读取按输入价格的 5% 计费，输出用量包含思考 token。[官方价格](https://aistudio.google.com/docs/pricing) · [长输出](https://aistudio.google.com/docs/long-decode)

## 配置
安装 Gemini 插件后,使用您从 Google 获取的 API 密钥进行配置。在模型提供商设置中输入密钥并保存。

![](./_assets/gemini-01.png)

如果您在 Gemini 和其他视觉模型中同时对 `MULTIMODAL_SEND_FORMAT` 使用 `url` 模式,可以设置 `Files URL` 以获得更好的性能。

`Enable request metadata` 为可选项,默认禁用。启用后,会将 `dify_app_id` 和 `dify_source` 作为 `labels` 附加到 `GenerateContentConfig` 的每次 Gemini 请求中,以便在 Cloud Billing 中将用量归因到特定的 Dify 应用。此选项仅适用于 `generate_content` 路由;Interactions API 不会在其账单明细中显示 labels,因此有意不受影响。Dify 会话查找采用尽力而为的方式:如果会话上下文未初始化,则不会附加任何 labels,请求将保持不变发送。


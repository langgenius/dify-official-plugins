# 概述

- [配置](#配置)

Gemini 是 Google 推出的多模态 AI 模型系列,旨在处理和生成各种类型的数据,包括文本、图像、音频和视频。此插件通过单个 API 密钥提供对 Gemini 模型的访问,使开发者能够构建多功能的多模态 AI 应用程序。

## 配置
安装 Gemini 插件后,使用您从 Google 获取的 API 密钥进行配置。在模型提供商设置中输入密钥并保存。

![](./_assets/gemini-01.png)

如果您在 Gemini 和其他视觉模型中同时对 `MULTIMODAL_SEND_FORMAT` 使用 `url` 模式,可以设置 `Files URL` 以获得更好的性能。


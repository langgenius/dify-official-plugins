# Dify Fish Audio 插件

## 简介

**Fish Audio** 是一个由 Fish Audio API 提供支持的高级文本转语音（TTS）工具。它能够将文本转换为高质量的语音，为各种使用场景提供可定制的语音选项。无论是构建虚拟助手、创建有声读物还是生成配音，Fish Audio 都能提供可靠且高效的 TTS 功能来增强您的应用程序。

## 配置

要开始使用 Fish Audio，请按照以下步骤操作：

1. **安装 Fish Audio 工具**
前往插件市场，安装 Fish Audio 工具，将其 TTS 功能集成到您的应用程序中。

2. **申请 Fish Audio API Key**
访问 [Fish Audio API Keys](https://fish.audio/zh-CN/go-api/api-keys) 页面生成 API Key。确保您的账户具有访问 TTS 服务的必要权限。

3. **授权 Fish Audio**
导航至 **工具 > Fish Audio > 去授权**，输入 API Key 以激活该工具。

![](./_assets/fishaudio-01.png)

## 工具功能

Fish Audio 工具提供一个主要功能：**TTS（文本转语音）**。

### TTS

使用 Fish Audio API 将文本转换为语音。要使用 TTS 功能，您需要提供以下参数：

* **Text**：您想要转换为语音的文本内容。
* **Voice ID**：用于生成语音的唯一语音标识符。Fish Audio 支持多种语音选项，允许进行自定义。

<img src="./_assets/fishaudio-02.png" width="400" />

## 使用方法

Fish Audio 可以无缝集成到 **聊天流 / 工作流应用** 和 **Agent 应用** 中。

### 聊天流 / 工作流应用

1. 将 Fish Audio TTS 节点添加到您的聊天流或工作流管道中。
2. 通过提供文本内容并选择 Voice ID 来配置节点。
3. 当管道运行时，TTS 功能生成语音音频，可以播放或作为工作流输出的一部分使用。

![](./_assets/fishaudio-03.png)

### Agent 应用

1. 将 Fish Audio TTS 工具添加到您的 Agent 应用程序中。
2. 在交互期间，通过聊天界面发送文本内容。
3. TTS 工具将把文本转换为语音并将生成的音频返回给用户。

![](./_assets/fishaudio-04.png)

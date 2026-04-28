# Azure OpenAI 图像生成与编辑

## 概述

Azure OpenAI 提供了 GPT-image 系列模型，可根据文本和图像输入生成或编辑图像。该插件支持基于当前 GPT-image 部署的 Azure OpenAI 图像生成与编辑工作流，包括最新的 `gpt-image-2` 部署。除通用的 Azure 图像工具外，插件现在还额外提供了独立的 `GPT Image 2 Generate` 和 `GPT Image 2 Edit` 工具，整体布局与 `tools/openai` 中的独立工具形式保持一致。本文档说明如何在 Dify 中配置并使用这些 Azure OpenAI 图像工具。

## 配置

### 1. 申请 Azure OpenAI API Key

请前往 [Azure OpenAI Platform](https://portal.azure.com/#home) 申请 API Key。这个 Key 将用于所有 Azure OpenAI 图像工具。

除了 API Key 之外，你还需要准备以下信息来配置插件：

- **Deployment Name**：Azure OpenAI GPT-image 部署名称，例如 `gpt-image-2`。
- **API Base URL**：Azure OpenAI 资源的基础地址，例如 `https://********.openai.azure.com/`。

### 2. 从插件市场安装 Azure OpenAI 图像工具

你可以在 **Plugin Marketplace** 中找到 Azure OpenAI 图像工具，例如 **Azure OpenAI Image Generate**、**Azure OpenAI Image Edit**、**GPT Image 2 Generate** 和 **GPT Image 2 Edit**。  
请安装你需要使用的工具。

### 3. 在 Dify 中填写配置

在 Dify 导航页中，点击 `Tools > [已安装的 Azure OpenAI Image Tool 名称] > Authorize`，然后填写所需字段。  
如果你有多个 Azure OpenAI 部署，请为每个部署分别重复配置。

可配置字段如下：

| 字段 | 说明 | 示例 |
| --- | --- | --- |
| **API Key** | 你的 Azure OpenAI API Key。 | `********************************` |
| **Deployment Name** | Azure OpenAI GPT-image 系列模型的部署名称。 | `gpt-image-2` |
| **API Base URL** | Azure OpenAI 资源的基础地址。请仅填写域名级别的 endpoint，**不要**带模型路径或查询参数。 | `https://********.openai.azure.com/` |
| **API Version** | 要使用的 Azure OpenAI API 版本。若要支持当前 GPT-image 编辑能力，请使用 `2025-04-01-preview` 或更高版本。 | `2025-04-01-preview` |

### 4. 使用工具

你可以在以下应用类型中使用 Azure OpenAI 图像工具：

#### Chatflow / Workflow 应用

Chatflow 和 Workflow 都支持添加已安装的 Azure OpenAI 图像工具节点，例如 `Azure OpenAI Image Generate`、`Azure OpenAI Image Edit`、`GPT Image 2 Generate` 和 `GPT Image 2 Edit`。添加节点后，你需要为必要输入项（如 “Prompt”）填写引用用户输入或前序节点输出的变量。最后，在 “End” 节点或后续节点中引用该工具输出的图像变量即可。

#### Agent 应用

在 Agent 应用设置中添加所需的 Azure OpenAI 图像工具。随后，在对话框中输入相应提示词（例如图像生成描述，或图像加编辑指令）来调用对应工具。如果你的 provider 配置指向 `gpt-image-2` 部署，也可以直接使用独立的 `GPT Image 2 Generate` 和 `GPT Image 2 Edit` 工具。Azure 官方文档将 variation 风格的能力归入图像编辑与 inpainting 工作流中，因此该插件提供的是生成与编辑工具，而不是单独的 variation endpoint 工具。

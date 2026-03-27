# Google Drive Trigger 插件用户指南

## 此插件的功能

- 当 Google Drive 通知我们文件或驱动器更改时，自动启动您的 Dify 工作流。
- 通过订阅 Google 的更改通知，无需轮询即可保持自动化同步。
- 让您通过在工作流内使用通配符模式匹配名称来缩小哪些文件重要。

## 步骤 1：使用 OAuth 连接您的 Google 账户

![Google Drive Trigger Plugin](./_assets/94938e90f2484db2762e14f8960991f3.png)

1. 在 Dify 中打开 Google Drive Trigger Plugin，点击 **New Subscription** → **Create with OAuth**。
2. 使用您要监控的 Google 账户登录并批准同意屏幕。Dify 的托管 OAuth 客户端（托管在 Dify Cloud 服务中）为您处理重定向和令牌存储。

> 提示：默认范围已经涵盖了更改通知（`https://www.googleapis.com/auth/drive.metadata.readonly https://www.googleapis.com/auth/drive.appdata`）。只有在您知道需要更广泛的访问权限时才更改它们。

### 可选：使用您自己的 OAuth 客户端

![Google Drive Trigger Plugin](./_assets/da494b82c5a2dd73db3709295fd7a383.png)

如果您的组织需要使用自己的 Google OAuth 凭据：

1. 访问 [Google Cloud Console](https://console.cloud.google.com/)，创建（或重用）一个项目，并启用 **Google Drive API**。
2. 在 **APIs & Services → Credentials** 中，创建一个 **OAuth client ID**（Web 应用程序）。
3. 当 Dify 要求授权重定向 URI 时，粘贴订阅对话框中显示的回调 URL，然后将生成的 **Client ID** 和 **Client Secret** 复制回 Dify。
4. 按照相同的同意流程重新连接—这次在提示时使用您的自定义客户端。

## 步骤 2：配置要监视的内容

在触发器订阅对话框中，您可以微调 Google Drive 发送更新的方式：

- **Spaces**（`drive`、`appDataFolder`）：选择您关心的 Drive 空间。如果您想要常规文件更改，"My Drive"必须保持选中状态。
- **Include removed items**：如果您需要捕获删除或移除，请启用。
- **Restrict to my drive**：将监视限制为您的个人 My Drive。保持关闭以监视共享驱动器或与您共享的文件。
- **Include items from all drives / Supports all drives**：如果您的自动化应对其他人或整个组织拥有的共享驱动器做出反应，请打开这些选项。

您可以随时重新访问这些设置以调整范围，而无需重做 OAuth 握手。

## 步骤 3：在工作流中使用触发器

1. 在 Dify 构建器中打开您的工作流，并添加 **Google Drive Change Detected** 触发器。
2. 在触发器节点中，使用 **File name pattern** 来决定哪些文件启动流程。模式支持通配符和多个条目（例如：`*.pdf, reports_??.xlsx`）。
3. 可选择 **Change types**（`file`、`drive`）以专注于文件元数据或共享驱动器级别的更改。
4. 发布工作流。Dify 保持监视通道活动，并将结构化的更改负载传递到您的下游节点。

> 示例：使用 `contracts/*.docx` 仅在 `contracts` 文件夹内的 Word 合同更改时运行审查自动化。

## 每个触发器中接收的内容

触发器返回来自 Google Drive Change API 的更改对象列表，包括：

- `changes`：每个条目包括 `change_type`、`file_id`、元数据如 `file.name`、所有者和时间戳。
- `subscription`：监视通道详细信息（`channel_id`、过期时间），以便您可以监控健康状况。
- `headers` & `body`：如果您需要验证或记录，由 Google 签名的原始 Webhook 包。

您可以将这些字段直接传递给工具、模型或其他工作流步骤，以构建验证、通知或同步作业。

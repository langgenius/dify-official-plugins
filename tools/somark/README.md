# SoMark Dify Plugin

## Overview / 简介

SoMark is a DocAI that can convert diverse documents—such as PDFs, images, and more—into structured Markdown or JSON. It is designed to work seamlessly across all scenarios.

SoMark 是一款 DocAI 产品，能够将各种文档（如 PDF、图片等）转换为结构化的 Markdown 或 JSON 格式。它旨在无缝适用于所有场景。

It breaks the traditional trade-off between accuracy, speed, and cost, delivering precise document parsing in milliseconds with minimal hardware resources.

它打破了传统 OCR 在准确性、速度和成本之间的权衡，以极少的硬件资源在毫秒级内提供精确的文档解析。

The resulting structured data is AI-native, ready to power LLM training, enhance RAG systems, and enable intelligent agents.

生成的结构化数据是 AI 原生的，可直接用于 LLM 训练、增强 RAG 系统和赋能智能体 (Agent)。

## Key Advantages / 核心优势

SoMark pioneers the proprietary 「OXR」algorithm, extending traditional OCR (Optical Character Recognition) into Optical Everything Recognition.

SoMark 首创了专有的「OXR」算法，将传统的 OCR（光学字符识别）扩展为 OXR（光学万物识别）。

From basic layout segmentation and reading-order recovery to complex elements such as tables, formulas, images, and even chemical notations, every component can be accurately extracted and reconstructed. The output is a complete, highly structured representation of the document.

从基础的版面分割和阅读顺序还原，到复杂的元素（如表格、公式、图片，甚至化学符号），所有组件都能被准确提取和重构。输出的是文档的完整、高度结构化的表示。

![](./_assets/somark-features.png)

Built on this powerful OXR algorithm, SoMark achieves the perfect balance of accuracy, speed, and cost:

基于强大的 OXR 算法，SoMark 实现了准确性、速度和成本的完美平衡：

- **Accurate / 精准**: Ultra-fine granularity— coordinate-traceable parsing for 21 document element types

  超细粒度——对 21 种文档元素类型进行坐标可追溯的解析
- **Fast / 快速**: Exceptional performance—parsing 100 pages in as little as 5 seconds

  卓越性能——解析 100 页仅需 5 秒
- **Economical / 经济**: Robust efficiency—private deployment can start with just a single RTX 3090

  高效能——私有化部署仅需单张 RTX 3090 即可启动

SoMark delivers strong general-purpose recognition capability. A single API call handles document parsing across all formats and scenarios.

SoMark 提供强大的通用识别能力。只需一个 API 调用即可处理所有格式和场景的文档解析。

### Supported Industries & Use Cases / 支持的行业与用例:

- **Finance / 金融**: research reports, financial statements, prospectuses

  研报、财报、招股书
- **Research / 科研**: academic papers, programming books, patent documents

  学术论文、编程书籍、专利文档
- **Education / 教育**: exam papers, workbooks, textbooks, scanned books

  试卷、教辅、教材、扫描书籍
- **Manufacturing / 制造**: forms, industrial manuals, engineering drawings

  表单、工业手册、工程图纸
- **Legal / 法律**: regulations, contracts, industry standards

  法规、合同、行业标准
- **Others / 其他**: white papers, PPTs, handwritten notes, vertical text, magazines, newspapers

  白皮书、PPT、手写笔记、竖排文本、杂志、报纸

### Supported File Formats / 支持的文件格式:

- **PDF & Images / PDF 与图片**: PDF, PNG, JPG/JPEG, BMP, TIFF, JP2, DIB, PPM, PGM, PBM, GIF, HEIC/HEIF, WEBP, XPM, TGA, DDS, XBM

## Unique Features / 独家功能

- **Image Understanding / 图像理解**: Comprehensively understands image content and generates accurate descriptions for pictures within documents.

  全面理解图像内容，并为文档中的图片生成准确描述。
- **Embedded Image Restoration / 嵌入式图像还原**: Recovers images embedded within text paragraphs and table cells, precisely presenting the original, complex information.

  还原嵌入在文本段落和表格单元格中的图片，精确呈现原始的复杂信息。
- **Watermark Resistance with Seal Recognition / 抗水印与印章识别**: Removes watermark interference, identifies seals/stamps, and extracts clean, pure content.

  去除水印干扰，识别印章/图章，提取干净纯粹的内容。
- **Heading Hierarchy Recognition / 标题层级识别**: Recognizes and extracts the hierarchy of headings in a document.

  识别文档中的标题层级，提取标题的层级结构。
- **Cross-Page Table Patching / 跨页表格合并**: Merges tables that span multiple pages, preserving the structure of the original document.

  合并跨页的表格，保留原始文档的表格结构。
- **Cross-Page Text Patching / 跨页文字合并**: Merges text that spans multiple pages, preserving the original document structure.

  合并跨页的文字，保留原始文档的结构。

## Next Steps and To-Do List / 后续计划与待办事项

### Expanded File Format Support / 扩展文件格式支持
- Spreadsheets / 电子表格: CSV, XLSX, XLSM, XLS, XLTX, XLTM, QPW
- Text Documents / 文档: DOC, DOCX, WPD, TXT
- Presentations / 演示文稿: PPTX, PPT, HTML

### New Advanced Features / 新增高级功能
- Auto Table Rotation / 自动表格旋转
- Statistical Charts to Tables / 统计图表转表格
- Multilingual Recognition & Parsing / 多语言识别与解析

## Getting Started / 快速开始

### Configuration Steps / 配置步骤

1.  Log into your Dify platform.

    登录您的 Dify 平台。
2.  Go to **"Tools" -> "Plugin Market"**, search for **"SoMark"** plugin and add it.

    前往 **"工具" -> "插件市场"**，搜索 **"SoMark"** 插件并添加。
3.  Configure the SoMark plugin parameters:

    配置 SoMark 插件参数：
    *   **Base URL**: Default is `https://somark.tech/api/v1`. You usually don't need to change this.

        默认为 `https://somark.tech/api/v1`。通常无需修改。
    *   **API Key**: Enter your SoMark API Key.

        输入您的 SoMark API Key。
        *   *No API Key?* [Get 1000 free pages here / 在此免费领取 1000 页额度](https://somark.tech/workbench/purchase)
4.  Save your configuration.

    保存配置。

### Usage in Workflow / 在工作流中使用

#### Step 1: Add the SoMark Tool Node / 第一步：添加 SoMark 工具节点

In your Dify workflow, click **"+"** to add a new node, select **"Tools"**, then find and add the **SoMark > Extract Document** node.

在 Dify 工作流中，点击 **"+"** 添加新节点，选择 **"工具"**，找到并添加 **SoMark > SoMark 文档解析** 节点。

![](./_assets/dify-添加SoMark工具节点.png)

#### Step 2: Configure Input Variables / 第二步：配置输入变量

In the **Extract Document** node panel, configure the **File** input:

在 **文档解析** 节点面板中，配置 **文件** 输入：

- Click the variable icon **`{x}`** in the **File** input field.
  点击 **文件** 输入框中的变量图标 **`{x}`**。
- Select the file variable you defined in the upstream node.
  选择您在上游节点中定义的文件变量。

For more parameters (such as output format and feature toggles), see **Input Parameters / 输入参数** below.

更多参数（如输出格式、功能开关等）请参考下方 **Input Parameters / 输入参数**。

**Note / 注意**:

- The API Key and Base URL are automatically injected from the plugin configuration — you do **not** need to enter them manually in the node.
- In self-hosted deployments, tool nodes run inside the plugin runtime (plugin-daemon). Ensure it can reach the configured Base URL (network egress / proxy / DNS). 

- API Key 和 Base URL 由插件配置自动注入，**无需**在节点中手动输入。
- 私有化部署时，工具节点在插件运行时（plugin-daemon）中执行。请确保该运行环境能够访问你配置的 Base URL（出网 / 代理 / DNS）。

![](./_assets/dify-配置输入变量.png)

#### Step 3: Reference the Output in Downstream Nodes / 第三步：在下游节点中引用输出

After the node executes, its output variables become available for all downstream nodes (e.g., LLM, Text Splitter, Code node). Click **`{x}`** in any downstream node's input field and select from the SoMark node's output variables.

节点执行完成后，其输出变量可在所有下游节点（如 LLM、文本分割、代码节点）中使用。在任意下游节点的输入框中点击 **`{x}`**，即可选择 SoMark 节点的输出变量。

#### Input Parameters / 输入参数

| Parameter / 参数 | Type / 类型   | Required / 必填 | Description / 描述 |
| :--------------- | :------------ | :-------------- | :----------------- |
| `File` (文件) | file          | Yes / 是        | Supported files: PDF, PNG, JPG, JPEG, BMP, TIFF, JP2, DIB, PPM, PGM, PBM, GIF, HEIC, HEIF, WEBP, XPM, TGA, DDS, XBM, DOC, DOCX, PPT, PPTX. Max 200 MB / 300 pages. <br> 支持的文件：PDF、PNG、JPG、JPEG、BMP、TIFF、JP2、DIB、PPM、PGM、PBM、GIF、HEIC、HEIF、WEBP、XPM、TGA、DDS、XBM、DOC、DOCX、PPT、PPTX。最大 200 MB / 300 页。 |
| `Output Formats` (输出格式) | checkbox      | No / 否         | Select one or more output formats. Supported options: `Markdown`, `JSON`. If left empty, the default outputs are `Markdown` and `JSON`. <br> 选择一个或多个输出格式。支持：`Markdown`、`JSON`。如果不选择，则默认输出 `Markdown` 和 `JSON`。 |
| `Image Format` (图片返回格式) | select    | No / 否         | Image output format. Supported options: `URL`, `Base64`, `None`. Default: `URL`. <br> 图片输出格式。支持：`URL`、`Base64`、`None`。默认值：`URL`。 |
| `Formula Format` (公式返回格式) | select  | No / 否         | Formula output format. Supported options: `LaTeX`, `MathML`, `ASCII`. Default: `LaTeX`. <br> 公式输出格式。支持：`LaTeX`、`MathML`、`ASCII`。默认值：`LaTeX`。 |
| `Table Format` (表格返回格式) | select    | No / 否         | Table output format. Supported options: `HTML`, `Markdown`, `Image`. Default: `HTML`. In Markdown mode, merged cells are expanded into individual cells with duplicated content. <br> 表格输出格式。支持：`HTML`、`Markdown`、`Image`。默认值：`HTML`。在 Markdown 模式下，合并单元格会被拆分为独立单元格，并填充相同内容。 |
| `Chemical Structure Formula Format` (化学结构式返回格式) | select       | No / 否         | Chemical structure output format. Supported options: `Image`. Default: `Image`. <br> 化学结构式输出格式。支持：`Image`。默认值：`Image`。 |
| `Enable Text Cross Page` (文字跨页拼接) | boolean | No / 否 | Merge text that spans across pages into a continuous paragraph. Default: `False`. <br> 将跨页文本合并为连续段落。默认值：`False`。 |
| `Enable Table Cross Page` (表格跨页拼接) | boolean | No / 否 | Merge tables that span across pages into a continuous table. Default: `False`. <br> 将跨页表格合并为连续表格。默认值：`False`。 |
| `Enable Title Level Recognition` (标题层级识别) | boolean | No / 否 | Recognize heading hierarchy such as H1/H2/H3. Default: `False`. <br> 识别标题层级结构，例如 H1/H2/H3。默认值：`False`。 |
| `Enable Inline Image` (保留文中图) | boolean | No / 否 | Return images embedded in text paragraphs. Default: `True`. <br> 返回文字段落中的图片。默认值：`True`。 |
| `Enable Table Image` (保留表中图) | boolean | No / 否 | Return images embedded in table cells. Default: `True`. <br> 返回表格单元格中的图片。默认值：`True`。 |
| `Enable Image Understanding` (图片理解) | boolean | No / 否 | Perform semantic understanding and structured description for images in the document. Default: `True`. <br> 对文档中的图片进行语义理解和结构化描述。默认值：`True`。 |
| `Keep Header Footer` (保留页眉页脚) | boolean | No / 否 | Keep page headers and footers instead of filtering them out. Default: `False`. <br> 保留页眉页脚而不是默认过滤掉。默认值：`False`。 |

#### Output Variables / 输出变量

The node exposes the following output variables:

节点暴露以下输出变量：

**`markdown`** `string` — The parsed document content in Markdown format, preserving the original layout structure including headings, tables, lists, formulas, and images. 

解析后的文档内容（Markdown 格式），保留原始版面结构，包括标题、表格、列表、公式和图片。

**`json_str`** `string` — The parsed document content in JSON string format, containing structured data for document
elements such as text blocks, tables, formulas, images, coordinates, and page information. Suitable for advanced
downstream processing in a Code node after JSON parsing.

解析后的文档内容（JSON 字符串格式），包含文本块、表格、公式、图片、坐标位置、页码等结构化信息。适合在代码节点中解析后做高级处理。

**`text`** / **`files`** — Dify built-in variables, not populated by this plugin.

Dify 内置变量，本插件不填充这两个变量。

## Credits / 致谢

This plugin interacts with the [SoMark API](https://somark.ai).

本插件基于 [SoMark API](https://somark.ai) 构建。

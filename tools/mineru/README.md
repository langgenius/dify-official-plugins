## MinerU Dify Plugin

MinerU is a tool that converts PDFs into machine-readable formats (e.g., markdown, JSON), allowing for easy extraction into any format. 

MinerU is a document parser that can parse complex document data for any downstream LLM use case (RAG, agents)

![](/Users/lidongyu/Library/Application%20Support/marktext/images/2025-03-11-15-26-23-image.png)

### GitHub

[GitHub - opendatalab/MinerU: A high-quality tool for convert PDF to Markdown and JSON.一站式开源高质量数据提取工具，将PDF转换成Markdown和JSON格式。](https://github.com/opendatalab/MinerU)



### Key Features

- Remove headers, footers, footnotes, page numbers, etc., to ensure semantic coherence.
- Output text in human-readable order, suitable for single-column, multi-column, and complex layouts.
- Preserve the structure of the original document, including headings, paragraphs, lists, etc.
- Extract images, image descriptions, tables, table titles, and footnotes.
- Automatically recognize and convert formulas in the document to LaTeX format.
- Automatically recognize and convert tables in the document to HTML format.
- Automatically detect scanned PDFs and garbled PDFs and enable OCR functionality.
- OCR supports detection and recognition of 84 languages.
- Supports multiple output formats, such as multimodal and NLP Markdown, JSON sorted by reading order, and rich intermediate formats.
- Supports various visualization results, including layout visualization and span visualization, for efficient confirmation of output quality.
- Supports running in a pure CPU environment, and also supports GPU(CUDA)/NPU(CANN)/MPS acceleration
- Compatible with Windows, Linux, and Mac platforms.

### Getting Started

    The plugin does not support the official MinerU API for now and only supports the locally deployed version.

Version 0.0.1 of the plugin corresponds to MinerU release 1.2.2.

1. Deploy Derived Projects

[MinerU/projects/web_api/README.md at magic_pdf-1.2.2-released · opendatalab/MinerU · GitHub](https://github.com/opendatalab/MinerU/blob/magic_pdf-1.2.2-released/projects/web_api/README.md)

2. Configure the server base url in your Dify plugin settings

### Input Parameters

| Parameter    | Type   | Required | Default | Description                               |
| ------------ | ------ | -------- | ------- | ----------------------------------------- |
| files        | files  | Yes      | -       | Files to be parsed                        |
| parse_method | select | Yes      | auto    | Parsing method, can be auto, ocr, or txt. |

### Output Format

The plugin provides three types of output for each processed file:

1. **Text Message**
   
   - Parsed PDF markdown text

2. **JSON Message**
   
   - Parsed PDF content list

3. **Blob Message**
   
   - The pictures extracted from the PDF.

## Credits

This plugin is powered by [MinerU]([GitHub - opendatalab/MinerU: A high-quality tool for convert PDF to Markdown and JSON.一站式开源高质量数据提取工具，将PDF转换成Markdown和JSON格式。](https://github.com/opendatalab/MinerU))

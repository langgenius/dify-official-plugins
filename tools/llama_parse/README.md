# LlamaParse Dify Plugin

LlamaParse is a GenAI-native document parser that can parse complex document data for any downstream LLM use case (RAG, agents). This plugin integrates LlamaParse capabilities into the Dify platform.

![LlamaParse screenshot](./_assets/llama_parse.png)

## Features

✅ **Broad file type support**: Parse various unstructured file types (.pdf, .pptx, .docx, .xlsx, .html) with text, tables, visual elements, and complex layouts.

✅ **Table recognition**: Accurately parse embedded tables into text and semi-structured representations.

✅ **Multimodal parsing**: Extract visual elements (images/diagrams) into structured formats using the latest multimodal models.

✅ **Custom parsing**: Customize output through custom prompt instructions.

## Getting Started

### API Key Setup

1. Visit [https://cloud.llamaindex.ai/api-key](https://cloud.llamaindex.ai/api-key) to create an account
2. Generate your API key
3. Configure the API key in your Dify plugin settings

### Usage Limits

- Free plan: Up to 1000 pages per day
- Paid plan: 7000 free pages per week + $0.003 per additional page

## Parameters

### Input Parameters

| Parameter   | Type    | Required | Default  | Description                                              |
| ----------- | ------- | -------- | -------- | -------------------------------------------------------- |
| files       | files   | Yes      | -        | Files to be parsed                                       |
| result_type | select  | No       | markdown | Output format (txt or md)                                |
| num_workers | number  | No       | 4        | Number of parallel workers for processing multiple files |
| verbose     | boolean | No       | false    | Enable detailed output logging                           |
| language    | string  | No       | "en"     | Output language (e.g., "en" for English)                 |

### Output Format

The plugin provides three types of output for each processed file:

1. **Text Message**

   - Plain text concatenation of all parsed documents, separated by "---"

2. **JSON Message**

   - Structure: `{ filename: [{ text: string, metadata: object }] }`
   - Contains parsed text and associated metadata for each document

3. **Blob Message**
   - Binary content with appropriate MIME type:
     - JSON: "application/json"
     - Markdown: "text/markdown"
     - Text: "text/plain"

## Credits

This plugin is powered by [LlamaParse](https://github.com/run-llama/llama_cloud_services/tree/main/llama_parse), a powerful document parsing service by LlamaIndex.

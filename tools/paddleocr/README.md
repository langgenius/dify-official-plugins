# PaddleOCR Dify Plugin

## Overview

**[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) is an industry-leading, production-ready OCR and document AI engine, offering end-to-end solutions from text extraction to intelligent document understanding.** This plugin provides several capabilities from PaddleOCR, including text recognition, document parsing, and more.

## Configuration

### 1. Get the PaddleOCR plugin from Plugin Marketplace

Open the Plugin Marketplace, search for the PaddleOCR plugin, and install it to integrate it with your application.

### 2. Fill in the configuration in Dify

Get an AI Studio access token from the [AI Studio Access Token page](https://aistudio.baidu.com/account/accessToken), then enter it in the plugin settings.

The optional **Base URL** setting is only needed when requests must pass through a custom gateway. Leave it empty to use the official PaddleOCR service.

### 3. Use the plugin

You can use the PaddleOCR plugin in the following application types. 

#### Chatflow / Workflow applications

Both Chatflow and Workflow applications support adding a PaddleOCR tool node.

#### Agent applications

Add a PaddleOCR tool in the Agent application, and then enter commands to call the tool.

The `file` input supports Dify uploaded image/PDF files directly and submits their contents to the PaddleOCR async job API. For compatibility with existing workflows, URL and base64 string values are still accepted by the runtime.

## Supported capabilities

| Tool | Supported models |
| --- | --- |
| Text Recognition | `PP-OCRv5` (default), `PP-OCRv5-latin`, `PP-OCRv6` |
| Document Parsing | `PP-StructureV3` |
| Large Model Document Parsing | `PaddleOCR-VL-1.6` (default), `PaddleOCR-VL-1.5`, `PaddleOCR-VL` |

All tools accept an optional PDF page range such as `2,4-6`. Both document parsing tools can skip Markdown image resources when they are not needed and can return an additional DOCX file alongside the Markdown and JSON results.

See the [PaddleOCR official API documentation](https://www.paddleocr.ai/latest/en/version3.x/inference_deployment/serving/paddleocr_official_api/cli.html) for the hosted service model matrix and request behavior.

## Credits

This plugin is powered by [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR).

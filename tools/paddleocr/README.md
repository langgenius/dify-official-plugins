# PaddleOCR Dify Plugin

## Overview

**[PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR) is an industry-leading, production-ready OCR and document AI engine, offering end-to-end solutions from text extraction to intelligent document understanding.** This plugin provides several capabilities from PaddleOCR, including text recognition, document parsing, and more.

## Configuration

### 1. Get the PaddleOCR plugin from Plugin Marketplace

Open the Plugin Marketplace, search for the PaddleOCR plugin, and install it to integrate it with your application.

### 2. Fill in the configuration in Dify

You can get your AI Studio access token from [this page](https://aistudio.baidu.com/index/accessToken).

For each tool provided by the plugin, there is a corresponding API URL. It is required to provide at least one API URL in order to use the PaddleOCR plugin. To obtain the API URL, visit the [PaddleOCR official website](https://aistudio.baidu.com/paddleocr), click the **API** button, choose the example code for the tool you want to use (e.g., *PP-OCRv5*), and copy the `API_URL`. You do not need to provide URLs for all tools—only for those you intend to use.

### 3. Use the plugin

You can use the PaddleOCR plugin in the following application types. 

#### Chatflow / Workflow applications

Both Chatflow and Workflow applications support adding a PaddleOCR tool node.

#### Agent applications

Add a PaddleOCR tool in the Agent application, and then enter commands to call the tool.

## Credits

This plugin is powered by [PaddleOCR](https://github.com/PaddlePaddle/PaddleOCR).

# Somark Dify Plugin

## Overview

Somark is a powerful document extraction tool that converts PDFs, Word documents, and images into high-quality Markdown, JSON, and other formats. This plugin allows you to integrate Somark's extraction capabilities directly into your Dify workflows.

## Key Features

- **High Accuracy**: Precise extraction of text, tables, formulas, and layouts.
- **Multiple Formats**: Supports input formats like PDF, JPG, PNG, DOC, DOCX, etc.
- **Structured Output**: Returns structured data (Markdown, JSON) suitable for RAG and LLM applications.

## Configuration

1. **Base URL**: The API endpoint for Somark. Default is `https://somark.tech/api/v1/extract`.
2. **API Key**: Your Somark API Key.

## Usage

1. Add the **Somark** tool to your workflow.
2. Upload a file to the `file` parameter.
3. The tool will return the extracted content (Markdown by default).

## Credits

This plugin interacts with the [Somark API](https://somark.tech).

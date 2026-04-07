# LiteParse Document Parser Node

**Author:** serdal  
**Version:** 0.0.1  
**Type:** Tool node for Dify

## 📄 Description

**LiteParse** is a high-performance document parsing tool powered by LlamaIndex's LlamaCloud. It goes beyond simple text extraction by converting complex documents—including PDFs with tables, multi-column layouts, and images—into clean, structured **Markdown**.

This node is ideal for RAG (Retrieval-Augmented Generation) pipelines where maintaining the original document structure and table formatting is critical for LLM accuracy.

---

## 🚀 Features

* **Complex Layout Support:** Accurately handles multi-column text and nested tables.
* **Markdown Output:** Returns clean Markdown that is optimized for LLM consumption.
* **OCR Capabilities:** Automatically processes scanned documents and images within PDFs.
* **Multiple Formats:** Supports `.pdf`, `.docx`, `.pptx`, and more via the LiteParse engine.

---

## 🛠️ Setup & Requirements

1.  **LlamaCloud API Key:** You must have an active API key from [LlamaCloud](https://cloud.llamaindex.ai/).
2.  **Dify Version:** Compatible with Dify's modern plugin architecture.

---

## 📥 Inputs

| Parameter | Type | Description |
| :--- | :--- | :--- |
| **LlamaCloud API Key** | `secret-input` | Your `llx-...` API key for authentication. |
| **Document File** | `file` | The document you wish to parse (PDF, DOCX, etc.). |

## 📤 Outputs

| Name | Type | Description |
| :--- | :--- | :--- |
| **Result** | `string` | The full content of the document converted to Markdown text. |

---

## 💡 Use Cases

* **Better RAG:** Convert messy PDFs into structured text to improve retrieval and answering.
* **Table Extraction:** Extract data from complex financial reports or academic papers without losing table alignment.
* **Data Pre-processing:** Clean up raw documents before feeding them into an LLM agent.

---

## ⚖️ License
This plugin is provided "as-is" under the same licensing terms as the original LiteParse library.

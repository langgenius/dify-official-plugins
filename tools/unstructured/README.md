# Unstructured for Dify

Use Unstructured to turn PDFs, DOCX, PPTX, HTML, images, and scanned documents into clean Markdown, JSON, HTML, or text. The Transform tool can also prepare documents for retrieval-augmented generation with enrichment, chunking, and embeddings.

## Tools

### Transform document

The recommended tool for new workflows. It connects to the hosted [Unstructured Transform MCP server](https://docs.unstructured.io/transform/overview), accepts either a Dify file or a public HTTP(S) URL, waits for the asynchronous job to finish, and returns the transformed output as both content and a downloadable file.

Set the provider fields as follows:

- **Server Type:** `Unstructured Transform`
- **API URL:** `https://mcp.transform.unstructured.io`
- **API Key:** A key from [Unstructured Transform](https://transform.unstructured.io/get-started)

The tool supports `auto`, `fast`, `hi_res`, and `vlm` parsing, optional enrichments, chunking, and embedding. See the [Transform quickstart](https://docs.unstructured.io/transform/quickstart) for account and usage details.

### Partition

The existing Partition tool remains available for legacy Partition API and self-hosted deployments. Configure its API URL and choose either **Local Deployment** or **Unstructured Official API**.

## Development

Install dependencies and run the standard Dify plugin entrypoint:

```bash
uv sync
uv run python -m main
```

Package the plugin from its parent directory:

```bash
dify plugin package ./unstructured
```

Source: [langgenius/dify-official-plugins](https://github.com/langgenius/dify-official-plugins/tree/main/tools/unstructured)

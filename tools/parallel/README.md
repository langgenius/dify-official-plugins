# Parallel Search MCP

Add live web search and clean URL fetching to Dify agents and workflows with [Parallel Search MCP](https://docs.parallel.ai/integrations/mcp/search-mcp).

## Tools

### Web Search

Search the current web from an agent's reasoning loop. Provide a focused objective and one or more concise keyword queries. The tool returns relevant source URLs and citation-ready excerpts.

### Web Fetch

Extract clean Markdown from specific HTTP or HTTPS URLs. By default, Parallel returns focused excerpts; enable full content only when the entire page is required.

## Configuration

No account or API key is required. Install the plugin from the Dify Marketplace and add **Web Search** or **Web Fetch** to an agent or workflow.

The plugin connects to the fixed anonymous Streamable HTTP endpoint at `https://search.parallel.ai/mcp`. Anonymous access is intended for exploration and light use. See the [Parallel Search MCP documentation](https://docs.parallel.ai/integrations/mcp/search-mcp) for current service details and higher-rate options.

Each response includes a `session_id`. Pass it to later Parallel Search or Fetch calls in the same conversation so the service can correlate related anonymous requests.

## Development

```bash
uv sync --all-groups --frozen --python 3.12
uv run --frozen pytest -q
uv run --frozen ruff format --check .
uv run --frozen ruff check .
```

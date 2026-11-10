# DeepSeek tools

Search the web and fetch page content through the official DeepSeek APIs.
This is a tool plugin for Dify Agents and workflows, independent of the DeepSeek model provider.
It can be used with `deepseek-flash` or any other tool-capable model.

## Configure

Get an API key from https://platform.deepseek.com/api_keys and configure it in this tool provider.
The key is the same kind used for the official DeepSeek model API; configure it separately here.
Credential validation calls `/models` and does not issue a paid search or fetch request.

## Tools

- **Search** calls `POST /v1/tools/search`. Supply `query` (1–128 characters),
  optionally `count` (1–50, default 10), `ori_question`, `need_content`, and `localization`.
  Operators such as `site:`, `lang:`, `after:`, and `before:` are supported.
  Returns the API's structured results as JSON and as text, including source URLs.
- **Fetch** calls `POST /v1/tools/fetch`. Supply an HTTP/HTTPS `url` (up to 8192 characters,
  without embedded credentials). Returns the title and Markdown content as JSON,
  and the Markdown body as text. Availability depends on the target site's access policy.

In an Agent, enable both tools so the model can search and read result pages as needed.
For Search, the model supplies `query` and optionally `ori_question`; configure
`count`, `need_content`, and `localization` in the tool settings.
In a workflow, add Search or Fetch nodes and pass their outputs to an LLM node.
These tools call the standalone APIs; they do not require Responses API built-in search.

Search and Fetch are billed separately from model tokens. See the
[API guide](https://api-docs.deepseek.com/zh-cn/guides/search/) and
[current pricing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/).

## Development

Run `uv sync --group dev`, then `uv run pytest tests -q` from this directory.
Tests mock all HTTP requests; no API key or paid requests are needed.

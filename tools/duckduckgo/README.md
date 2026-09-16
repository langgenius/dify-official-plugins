# Duckduckgo

## Overview

DuckDuckGo is a search engine focused on privacy. This plugin offers web page search and image search.

> **Note:** the AI Chat and Translate tools are deprecated and no longer functional. DuckDuckGo removed the endpoints they depended on, and the maintained search library this plugin uses (`ddgs`) provides no replacement. They remain registered so existing workflows still load, but calling them raises an explanatory error. Use an LLM node or a dedicated translation tool instead.

## Configuration

### 1. Get DuckDuckGo tools from Plugin Marketplace

The DuckDuckGo tools could be found at the Plugin Marketplace, please install it first.

![](./_assets/duckduckgo_1.PNG)

### 2. Use the tool

You can use the DuckDuckGo tool in the following application types.

![](./_assets/duckduckgo_2.PNG)

#### - Chatflow / Workflow applications

Both Chatflow and Workflow applications support adding DuckDuckGo tool nodes. Two tools are functional: simple search and image search. The ai chatbox and translation tools are deprecated (see the note above).

#### - Agent applications

Add the DuckDuckGo tool in the Agent application, then enter the search command to call this tool.

## Rate limiting and blocked hosts

`ddgs` scrapes public search engines rather than calling an API, so a host that runs many searches in a short window (for example a workflow that loops over several search nodes) gets rate-limited or served captcha pages. When that happens the tool raises `DuckDuckGo text search returned nothing for '...' after 3 attempts`.

The plugin already spaces searches 2 seconds apart per process and retries with exponential backoff. If you still hit the error:

- **Reduce volume.** Merge overlapping queries into one search node and lower loop counts.
- **Pin `Search engines`.** Set it to a comma-separated list of engines that still answer from your host, e.g. `duckduckgo,brave,yahoo`. Leave empty to rotate through all of them.
- **Set `Proxy server`.** Route through an http/https/socks proxy (rotating proxies work best), or `tb` for a local Tor Browser.
- **Handle failures in the workflow.** Enable *Retry on failure* and an *Error handling* strategy on the tool node so one blocked search degrades instead of aborting the run.

For sustained high-volume use, an API-backed search plugin (Tavily, Serper, Brave Search, SearXNG) is more reliable than scraping.

## brightdata_datasource

**Author:** langgenius
**Version:** 0.1.3
**Type:** datasource

# Bright Data Web Scraper

A Dify plugin that enables enterprise-grade web scraping with Bright Data's Unlocker API. Extract data from any website, bypass anti-bot protection, and access structured data from 50+ platforms including Amazon, LinkedIn, Instagram, and more.

## Features

- **Universal Web Access**: Scrape any webpage, even those with bot detection or CAPTCHA
- **Multiple Formats**: Output in Markdown or HTML format
- **PDF Support**: Extract content from PDF files
- **Enterprise-Grade**: Powered by Bright Data's reliable infrastructure

## Configuration

### Prerequisites

1. **Bright Data Account**: Sign up at [Bright Data](https://brightdata.com)
2. **Unlocker API Zone**: Create a new zone in your Bright Data dashboard at https://brightdata.com/cp/zones/new
3. **API Token**: Generate an API token from your user settings

### Setup

1. Install the plugin in your Dify workspace
2. Configure the following credentials:
   - **Unlocker API Zone**: Your Bright Data zone identifier
   - **Bright Data API Token**: Your API authentication token

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `url` | string | Yes | The full URL of the webpage to scrape |
| `format` | select | Yes | Output format: `markdown` or `html` (default: markdown) |

### Output Schema

The plugin returns an array of objects containing:
- `source_url`: The original URL that was scraped
- `content`: The extracted content in the specified format
- `title`: The title of the webpage
- `description`: A description of the content

## Usage

Simply provide a URL and the plugin will return the scraped content in your preferred format, ready for use with LLMs or other applications.

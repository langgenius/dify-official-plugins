# Firecrawl Datasource Plugin

**Author**: langgenius  
**Version**: 0.2.3 
**Type**: datasource (website_crawl)

## Introduction

This plugin integrates with Firecrawl, a powerful web scraping and crawling API service that recursively searches through URLs and subdomains to gather structured content. Firecrawl provides clean, LLM-ready data extraction with advanced filtering options, making it ideal for building knowledge bases, monitoring websites, and extracting structured information for AI applications like Dify.

## Features

- **Recursive Web Crawling**: Automatically crawl websites and their subpages
- **Depth Control**: Configure maximum crawl depth relative to the starting URL
- **Smart Content Extraction**: Extract only main content, excluding headers, footers, and navigation
- **URL Pattern Filtering**: Include or exclude specific URL patterns
- **Page Limit Control**: Set maximum number of pages to crawl
- **Real-time Progress Tracking**: Monitor crawl status and completion
- **Clean Markdown Output**: Convert web content to structured, LLM-friendly format
- **Self-Hosted Support**: Use Firecrawl cloud or your own instance

## Setup

### Prerequisites

Before using this plugin, you need:
1. A Firecrawl API key (for cloud service) or self-hosted Firecrawl instance
2. Target URLs ready for crawling
3. Understanding of your crawling requirements (depth, limits, patterns)

### Configuration Steps

#### Option 1: Using Firecrawl Cloud Service

1. **Get a Firecrawl API Key**:
   - Visit [Firecrawl](https://firecrawl.dev)
   - Sign up for an account
   - Navigate to your [account settings](https://www.firecrawl.dev/account)
   - Copy your API key

2. **Configure the Plugin in Dify**:
   - Navigate to the datasource plugins section in Dify
   - Select Firecrawl
   - **Base URL**: Leave empty or enter `https://api.firecrawl.dev`
   - **API Key**: Enter your Firecrawl API key
   - Click "Save" to store the configuration

#### Option 2: Using Self-Hosted Firecrawl

1. **Deploy Firecrawl**:
   - Follow the [self-hosting guide](https://docs.firecrawl.dev/self-host)
   - Note your instance URL

2. **Configure the Plugin in Dify**:
   - Navigate to the datasource plugins section in Dify
   - Select Firecrawl
   - **Base URL**: Enter your self-hosted Firecrawl URL (e.g., `https://firecrawl.your-domain.com`)
   - **API Key**: Enter any key (required by the plugin but can be arbitrary for self-hosted)
   - Click "Save" to store the configuration

## Usage

### Basic Single Page Extraction

To extract content from a single page without crawling subpages:

**Parameters:**
- **Start URL** (required): `https://example.com/article`
- **Crawl Subpages**: `false`
- **Maximum pages to crawl**: `1`
- **Only Main Content**: `true`

### Full Website Crawling

To crawl an entire website with subpages:

**Parameters:**
- **Start URL** (required): `https://example.com`
- **Crawl Subpages**: `true`
- **Maximum crawl depth**: `2` (crawls up to 2 levels deep)
- **Maximum pages to crawl**: `50`
- **Only Main Content**: `false`

### Targeted Section Crawling

To crawl only specific sections of a website:

**Parameters:**
- **Start URL**: `https://example.com`
- **Crawl Subpages**: `true`
- **URL patterns to include**: `blog/*, docs/*`
- **URL patterns to exclude**: `archive/*, tag/*`
- **Maximum pages to crawl**: `30`

## Parameters Explained

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `url` | string | Yes | - | The base URL to start crawling from |
| `crawl_subpages` | boolean | No | true | Whether to crawl subpages |
| `exclude_paths` | string | No | - | Comma-separated patterns to exclude (e.g., `blog/*, about/*`) |
| `include_paths` | string | No | - | Comma-separated patterns to include (e.g., `docs/*, api/*`) |
| `max_depth` | number | No | 2 | Maximum depth to crawl (0 = only start URL) |
| `limit` | number | No | 10 | Maximum number of pages to crawl |
| `only_main_content` | boolean | No | false | Extract only main content, excluding navigation elements |

### Understanding Crawl Depth

- **Depth 0**: Only the entered URL
- **Depth 1**: The entered URL + all directly linked pages
- **Depth 2**: The entered URL + directly linked pages + pages linked from those
- Higher values follow the same pattern

### URL Pattern Examples

**Include Patterns:**
- `blog/*` - Include all blog pages
- `docs/api/*` - Include API documentation
- `products/*/specs` - Include all product specification pages

**Exclude Patterns:**
- `admin/*` - Exclude admin pages
- `*.pdf` - Exclude PDF files
- `tag/*,category/*` - Exclude tag and category pages

## Output Format

The plugin returns structured data for each crawled page:

```json
{
  "source_url": "https://example.com/page",
  "title": "Page Title",
  "description": "Meta description of the page",
  "content": "Clean markdown formatted content..."
}
```

## How It Works

1. **Job Creation**: The plugin creates a crawl job with Firecrawl API
2. **Asynchronous Crawling**: Firecrawl processes the website based on your parameters
3. **Status Monitoring**: The plugin polls for job status every 5 seconds
4. **Content Processing**: Completed pages are formatted and structured
5. **Result Delivery**: Clean, structured content is returned

## Use Cases

### 1. Documentation Indexing
Crawl technical documentation sites for AI-powered search:
```
URL: https://docs.example.com
Include paths: api/*, guides/*
Max depth: 3
Limit: 100
```

### 2. Blog Content Extraction
Extract all blog posts for content analysis:
```
URL: https://blog.example.com
Include paths: posts/*, articles/*
Exclude paths: tag/*, author/*
Only main content: true
```

### 3. Product Catalog Building
Gather product information from e-commerce sites:
```
URL: https://shop.example.com/products
Max depth: 2
Limit: 50
Only main content: true
```

### 4. Competitor Monitoring
Track competitor website changes:
```
URL: https://competitor.com
Include paths: products/*, pricing/*
Exclude paths: blog/*, news/*
Max depth: 2
```

## Best Practices

1. **Start Small**: Begin with lower limits and depths for testing
2. **Use Pattern Filtering**: Focus crawling with include/exclude patterns
3. **Respect Robots.txt**: Ensure target sites allow crawling
4. **Monitor Progress**: Check crawl status for large operations
5. **Extract Main Content**: Use `only_main_content` for cleaner data
6. **Set Appropriate Limits**: Balance comprehensiveness with efficiency
7. **Test Patterns**: Verify your URL patterns match intended pages

## Performance Considerations

- **Large Sites**: May take several minutes to crawl
- **Deep Crawling**: Exponentially increases pages (be cautious with depth > 3)
- **Rate Limiting**: Firecrawl handles rate limiting automatically
- **Concurrent Jobs**: Multiple crawl jobs can run simultaneously

## Troubleshooting

### Common Issues

1. **"API key is required" error**:
   - Verify your API key is correctly entered
   - Check if using the correct base URL

2. **"Failed to crawl" error**:
   - Check if the target URL is accessible
   - Verify your API key is valid
   - Ensure you haven't exceeded rate limits

3. **Incomplete crawling**:
   - Some sites may block automated crawling
   - JavaScript-heavy sites might not render fully
   - Check if robots.txt restricts access

4. **Slow crawling**:
   - Large sites naturally take longer
   - Consider reducing depth or page limits
   - Use pattern filtering to focus crawling

5. **Missing pages**:
   - Verify include/exclude patterns are correct
   - Check if pages are within specified depth
   - Ensure limit hasn't been reached

6. **Self-hosted connection issues**:
   - Verify base URL is correct and accessible
   - Check firewall/network settings
   - Ensure SSL certificates are valid

## API Limits

### Firecrawl Cloud
- Rate limits based on your plan
- Check your [account dashboard](https://www.firecrawl.dev/account) for usage

### Self-Hosted
- No external rate limits
- Performance depends on your infrastructure

## Security Considerations

- API keys are transmitted securely via HTTPS
- Use environment variables for API key storage in production
- For sensitive data, consider self-hosting
- Review crawled content for any inadvertently captured sensitive information

## Privacy

Please refer to the [Privacy Policy](PRIVACY.md) for information on how your data is handled when using this plugin.

## Support

For issues or questions:
- **Plugin Support**: [hello@dify.ai](mailto:hello@dify.ai)
- **Firecrawl Documentation**: [https://docs.firecrawl.dev](https://docs.firecrawl.dev)
- **Firecrawl Support**: Visit [Firecrawl](https://firecrawl.dev)

## Additional Resources

- [Firecrawl API Reference](https://docs.firecrawl.dev/api-reference)
- [Self-Hosting Guide](https://docs.firecrawl.dev/self-host)
- [Firecrawl GitHub](https://github.com/mendableai/firecrawl)

## Updates and Changelog

**Version 0.2.2** (Current)
- Enhanced pattern filtering
- Improved error handling
- Better progress tracking
- Self-hosted instance support

Last updated: December 2024

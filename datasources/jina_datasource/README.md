# Jina Reader Datasource Plugin

**Author**: langgenius  
**Version**: 0.0.4  
**Type**: datasource (website_crawl)

## Introduction

This plugin integrates with Jina AI's Reader API to fetch and convert web content into LLM-friendly markdown format. It supports crawling websites, extracting content from web pages and PDFs, and processing the information for use in AI applications like Dify. The plugin provides intelligent web scraping capabilities with automatic content extraction and formatting.

## Features

- **Web Page to Markdown Conversion**: Automatically converts web pages to clean, LLM-friendly markdown
- **PDF Support**: Extract and convert content from PDF documents
- **Smart Crawling**: Crawl websites with configurable depth and page limits
- **Sitemap Support**: Utilize sitemaps for efficient website crawling
- **Subpage Crawling**: Optionally crawl and process subpages from the main URL
- **Real-time Progress Tracking**: Monitor crawling progress with status updates
- **Clean Content Extraction**: Remove ads, navigation, and other non-content elements

## Setup

### Prerequisites

Before using this plugin:
1. (Optional) Obtain a Jina AI API key for higher rate limits
2. Have target URLs ready for crawling
3. Ensure target websites allow crawling (check robots.txt)

### Configuration Steps

1. **Get a Jina AI API Key** (Optional but Recommended):
   - Visit [Jina AI](https://jina.ai)
   - Sign up for an account
   - Navigate to your dashboard to get your API key
   - Note: The plugin works without an API key but with lower rate limits

2. **Configure the Plugin in Dify**:
   - Navigate to the datasource plugins section in Dify
   - Select Jina Reader
   - Enter your **API Key** (optional - leave empty if you don't have one)
   - Click "Save" to store the configuration

## Usage

### Basic Web Page Extraction

To extract content from a single web page:

**Parameters:**
- **Start URL** (required): The web page URL to extract content from
- **Crawl Subpages**: Set to `false` for single page extraction
- **Maximum Pages**: Set to `1` for single page
- **Use Sitemap**: Set to `false` for direct extraction

**Example:**
```
URL: https://example.com/article
Crawl Subpages: false
Maximum Pages: 1
Use Sitemap: false
```

### Website Crawling

To crawl multiple pages from a website:

**Parameters:**
- **Start URL** (required): The base URL to start crawling
- **Crawl Subpages**: Set to `true` to crawl linked pages
- **Maximum Pages**: Number of pages to crawl (default: 10)
- **Use Sitemap**: Set to `true` to use the website's sitemap

**Example:**
```
URL: https://example.com
Crawl Subpages: true
Maximum Pages: 50
Use Sitemap: true
```

### PDF Content Extraction

The plugin automatically detects and processes PDF URLs:

**Example:**
```
URL: https://example.com/document.pdf
Crawl Subpages: false
Maximum Pages: 1
Use Sitemap: false
```

## Parameters Explained

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `url` | string | Yes | - | The starting URL for crawling |
| `crawl_sub_pages` | boolean | No | true | Whether to crawl linked subpages |
| `limit` | number | No | 10 | Maximum number of pages to crawl |
| `use_sitemap` | boolean | No | false | Use the website's sitemap for crawling |

## Output Format

The plugin returns structured data for each crawled page:

```json
{
  "source_url": "https://example.com/page",
  "title": "Page Title",
  "description": "Meta description of the page",
  "content": "Markdown formatted content..."
}
```

## How It Works

1. **Job Initiation**: When you provide a URL, the plugin creates a crawling job with Jina AI
2. **Crawling Process**: Jina AI's crawler visits the specified pages
3. **Content Extraction**: The Reader API extracts main content, removing clutter
4. **Markdown Conversion**: Content is converted to clean, structured markdown
5. **Status Updates**: The plugin provides real-time progress updates
6. **Result Delivery**: Processed content is returned in a structured format

## Use Cases

### 1. Knowledge Base Building
Extract documentation from websites to build knowledge bases:
- Technical documentation sites
- API references
- Help centers

### 2. Research and Analysis
Gather information from multiple web sources:
- News articles
- Blog posts
- Academic papers (PDFs)

### 3. Content Migration
Convert web content for use in AI applications:
- Website content to chatbot knowledge
- Blog posts to training data
- Documentation to Q&A systems

### 4. Competitive Analysis
Monitor and analyze competitor websites:
- Product pages
- Pricing information
- Feature documentation

## Best Practices

1. **Respect Website Policies**:
   - Check robots.txt before crawling
   - Respect rate limits
   - Don't overload servers with excessive requests

2. **Optimize Crawling**:
   - Start with smaller page limits for testing
   - Use sitemaps when available for better coverage
   - Focus crawling on relevant sections

3. **API Key Management**:
   - Keep your API key secure
   - Monitor usage to stay within limits
   - Consider upgrading for higher rate limits if needed

4. **Content Quality**:
   - Review extracted content for completeness
   - Verify important information is captured
   - Check for any formatting issues

## Limitations

- **Rate Limits**: Without API key: lower rate limits; With API key: higher limits based on plan
- **JavaScript Content**: Dynamic content may not be fully captured
- **Authentication**: Cannot access password-protected content
- **File Types**: Primarily supports HTML and PDF formats
- **Crawl Depth**: Limited by the maximum pages parameter

## Troubleshooting

### Common Issues

1. **"Failed to crawl" error**:
   - Check if the URL is accessible
   - Verify your API key is valid (if provided)
   - Ensure you haven't exceeded rate limits

2. **Incomplete content extraction**:
   - Some websites may have anti-scraping measures
   - JavaScript-rendered content might not be captured
   - Try adjusting crawl parameters

3. **Slow crawling speed**:
   - Large websites take time to process
   - Consider reducing the page limit
   - Use sitemap for more efficient crawling

4. **Missing subpages**:
   - Ensure "Crawl Subpages" is enabled
   - Check if the limit is sufficient
   - Verify links are discoverable (not behind JavaScript)

5. **API key issues**:
   - Verify the API key is correctly entered
   - Check if the key is active and not expired
   - Monitor your usage quota

## Pricing

- **Free Tier**: Works without API key with basic rate limits
- **With API Key**: Higher rate limits and priority processing
- Visit [Jina AI Pricing](https://jina.ai) for current pricing information

## Performance Tips

1. **For Large Websites**:
   - Use sitemaps when available
   - Set reasonable page limits
   - Consider breaking crawls into sections

2. **For Better Results**:
   - Provide specific URLs rather than homepages when possible
   - Disable subpage crawling for single article extraction
   - Use the API key for more reliable service

3. **For PDFs**:
   - Direct PDF URLs work best
   - Large PDFs may take longer to process
   - Ensure PDFs are publicly accessible

## Privacy and Security

- Content is processed through Jina AI's secure infrastructure
- No permanent storage of crawled content by the plugin
- API keys are transmitted securely via HTTPS
- See [Privacy Policy](PRIVACY.md) for detailed information

## Support

For issues or questions:
- Contact: [hello@dify.ai](mailto:hello@dify.ai)
- Jina AI Documentation: [https://jina.ai/reader](https://jina.ai/reader)
- Repository: Check the project repository for updates

## Additional Resources

- [Jina AI Reader Documentation](https://jina.ai/reader)
- [Jina AI API Reference](https://docs.jina.ai)
- [Web Scraping Best Practices](https://jina.ai/blog)

## Updates and Changelog

**Version 0.0.3** (Current)
- Improved crawling stability
- Better error handling
- Enhanced progress tracking

Last updated: December 2024

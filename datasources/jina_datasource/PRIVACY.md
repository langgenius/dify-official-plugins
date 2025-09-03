# Privacy Policy

This Privacy Policy explains how we collect, use, and protect your information when you use the Jina Reader Datasource Plugin for Dify.

## Information Collection

We do not collect, store, or share any personal information from users. All data processed by the plugin is handled locally or through secure connections to Jina AI's Reader API services, as required for functionality.

## Use of Information

The plugin only accesses publicly available web content to provide the requested features:
- Converting web pages to LLM-friendly markdown format
- Extracting content from PDFs and other web documents
- Crawling specified websites with user-defined limits
- Processing sitemaps when enabled

No personal data is collected, stored, or transmitted to third parties by the plugin itself.

## Data Processing

When using this plugin:
- **URL Processing**: The target URLs you provide are sent to Jina AI's Reader API for processing
- **Content Extraction**: Web page content is extracted and converted to markdown format
- **Crawling Scope**: Only the specified URLs and subpages (when enabled) are accessed
- **Temporary Processing**: Data is processed in real-time and not permanently stored by the plugin

## Third-Party Services

This plugin interacts with Jina AI's Reader API services:
- **Service Endpoints**: 
  - `https://r.jina.ai/` (Reader endpoint)
  - `https://adaptivecrawl-kir3wx7b3a-uc.a.run.app` (Crawl initiation)
  - `https://adaptivecrawlstatus-kir3wx7b3a-uc.a.run.app` (Status checking)
- Please refer to [Jina AI's Privacy Policy](https://jina.ai/privacy) for details on how your data is handled by Jina services

## API Key Usage

- **Optional Authentication**: API key is optional but provides higher rate limits
- **Secure Transmission**: API keys are transmitted securely via HTTPS
- **Session-Only Storage**: API keys are only stored for the duration of your session
- **No Key Logging**: The plugin does not log or permanently store your API key

## Data Security

We are committed to ensuring the security of your data:
- All communications with Jina AI services use secure HTTPS protocols
- Authentication tokens (when provided) are handled securely
- No crawled content is permanently stored by the plugin
- Data is transmitted directly between your system and Jina AI services

## Content Access Scope

The plugin accesses only:
- Publicly available web pages at the URLs you specify
- Subpages of the target URL (when crawl_sub_pages is enabled)
- Sitemap data (when use_sitemap is enabled)
- Content that is accessible without authentication

The plugin does NOT:
- Access password-protected or private content
- Store crawled data permanently
- Share crawled content with unauthorized parties
- Access content beyond the specified limits

## User Rights

You have the right to:
- Control which websites are crawled
- Set limits on the number of pages processed
- Choose whether to use an API key
- Decide whether to crawl subpages or use sitemaps
- Stop the crawling process at any time

## Compliance

This plugin respects:
- Website robots.txt files and crawling policies
- Rate limiting and ethical crawling practices
- Copyright and intellectual property rights
- Data protection regulations

## Data Retention

- **No Long-term Storage**: The plugin does not retain crawled content after processing
- **Session Data**: Temporary data is cleared after each session
- **Job Status**: Crawling job status is tracked only during active operations

## Changes to This Policy

We may update this Privacy Policy from time to time. Any changes will be posted in this document with an updated effective date.

## Contact

If you have any questions or concerns about this Privacy Policy, please contact the developer [hello@dify.ai](mailto:hello@dify.ai) or refer to the project repository for more information.

Last updated: December 2024

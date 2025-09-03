# Privacy Policy

This Privacy Policy explains how we collect, use, and protect your information when you use the Firecrawl Datasource Plugin for Dify.

## Information Collection

We do not collect, store, or share any personal information from users. All data processed by the plugin is handled locally or through secure connections to Firecrawl API services, as required for functionality.

## Use of Information

The plugin only accesses publicly available web content to provide the requested features:
- Recursively crawling websites and subdomains
- Extracting and structuring web page content
- Filtering content based on URL patterns
- Converting web content to clean, structured markdown format

No personal data is collected, stored, or transmitted to third parties by the plugin itself.

## Data Processing

When using this plugin:
- **URL Processing**: Target URLs are sent to Firecrawl's API for processing
- **Content Extraction**: Web page content is extracted and converted to structured format
- **Crawling Scope**: Only specified URLs and their subpages (based on your settings) are accessed
- **Temporary Processing**: Data is processed in real-time and not permanently stored by the plugin
- **Content Filtering**: Main content can be extracted while excluding headers, footers, and navigation

## Third-Party Services

This plugin interacts with Firecrawl API services:
- **Default Service Endpoint**: `https://api.firecrawl.dev`
- **Self-hosted Option**: You can use your own Firecrawl instance
- Please refer to [Firecrawl's Privacy Policy](https://firecrawl.dev/privacy) for details on how your data is handled by Firecrawl services

## API Key Security

- **Required Authentication**: API key is required for service access
- **Secure Transmission**: API keys are transmitted securely via HTTPS
- **Session-Only Storage**: API keys are only stored for the duration of your session
- **No Key Logging**: The plugin does not log or permanently store your API key
- **Self-hosted Support**: For self-hosted instances, you control your own authentication

## Data Security

We are committed to ensuring the security of your data:
- All communications with Firecrawl services use secure HTTPS protocols
- Bearer token authentication ensures secure API access
- No crawled content is permanently stored by the plugin
- Data is transmitted directly between your system and Firecrawl services
- Idempotency keys can be used to prevent duplicate operations

## Content Access Scope

The plugin accesses only:
- Publicly available web pages at the URLs you specify
- Subpages within the specified crawl depth
- Content matching your include patterns (if specified)
- Content not matching your exclude patterns (if specified)

The plugin does NOT:
- Access password-protected or private content
- Store crawled data permanently
- Share crawled content with unauthorized parties
- Exceed the page limits you specify
- Access content beyond the specified depth

## User Rights

You have the right to:
- Control which websites are crawled
- Set crawl depth and page limits
- Define URL patterns to include or exclude
- Choose between cloud or self-hosted service
- Cancel crawling operations at any time
- Request only main content extraction

## Compliance

This plugin respects:
- Website robots.txt files and crawling policies
- Rate limiting and ethical crawling practices
- Copyright and intellectual property rights
- Data protection regulations
- Website terms of service

## Data Retention

- **No Long-term Storage**: The plugin does not retain crawled content after processing
- **Session Data**: Temporary data is cleared after each session
- **Job Status**: Crawling job status is tracked only during active operations
- **Cache**: No caching of crawled content is performed by the plugin

## Self-Hosted Deployments

For self-hosted Firecrawl instances:
- You have complete control over data processing
- Data never leaves your infrastructure
- You manage your own security and privacy policies
- The plugin respects your self-hosted instance's configuration

## Changes to This Policy

We may update this Privacy Policy from time to time. Any changes will be posted in this document with an updated effective date.

## Contact

If you have any questions or concerns about this Privacy Policy, please contact the developer [hello@dify.ai](mailto:hello@dify.ai) or refer to the project repository for more information.

Last updated: December 2024

# Tavily Search & Extract Datasource Plugin

A Dify datasource plugin that uses Tavily's powerful search and content extraction APIs to find and extract content from web pages.

## Features

- **Web Search**: Search the web using Tavily's advanced search API
- **Content Extraction**: Extract clean, readable content from web pages
- **Multiple Topics**: Support for general, news, finance, and legal search topics
- **Domain Filtering**: Include or exclude specific domains from search results
- **AI Answers**: Get AI-generated answers based on search results
- **Image Support**: Optionally include images in search results
- **Advanced Options**: Choose between basic and advanced search depth

## Configuration

### API Key

You'll need a Tavily API key to use this plugin. Get one from [Tavily](https://app.tavily.com/).

### Search Parameters

- **Search Query**: The main search query to find relevant web pages
- **Search Depth**: Choose between "basic" (faster) or "advanced" (more comprehensive)
- **Search Topic**: Select from general, news, finance, or legal topics
- **Max Results**: Number of search results to return (1-20)
- **Domain Filters**: Include or exclude specific domains
- **Include Images**: Whether to include images in results
- **Include Answer**: Whether to include AI-generated answers
- **Include Raw Content**: Whether to extract full content from found pages

## Usage

1. Configure your Tavily API key in the datasource settings
2. Enter your search query
3. Adjust search parameters as needed
4. Run the datasource to get search results and extracted content

## Search Topics

- **General**: Standard web search across all types of content
- **News**: Recent news articles and updates
- **Finance**: Financial information, market data, and related content
- **Legal**: Legal documents, regulations, and court information

## Output Format

The plugin returns:
- **Status**: Current status of the search operation
- **Web Info List**: List of found web pages with extracted content
- **Total/Completed**: Progress tracking
- **AI Answer**: Generated answer based on search results (if enabled)

Each web page entry includes:
- Source URL
- Title
- Description (with relevance score and publish date if available)
- Extracted content

## Version

**v0.1.0** - Initial release of Tavily Search & Extract datasource plugin

## Requirements

- Tavily API key
- Internet connection for API calls
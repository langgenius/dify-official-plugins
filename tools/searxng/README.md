# SearXNG Search Plugin for Dify

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://python.org)
[![Dify Plugin](https://img.shields.io/badge/dify-plugin-green.svg)](https://dify.ai)

## Overview

**SearXNG** is a free, open-source, and privacy-respecting metasearch engine that aggregates results from over 70 search services and databases. Unlike traditional search engines, SearXNG doesn't track users or build profiles, ensuring complete anonymity while delivering comprehensive search results.

This Dify plugin integrates SearXNG's powerful search capabilities directly into your Dify workflows, enabling you to:
- Perform anonymous searches across multiple engines simultaneously
- Access diverse content types (web, images, videos, news, maps, music, etc.)
- Retrieve aggregated results without compromising user privacy
- Filter results by time range and content categories

### Key Features

- **🔒 Privacy-First**: No tracking, profiling, or data collection
- **🌐 Multi-Engine**: Aggregates results from 70+ search services
- **📊 Versatile Search Types**: General, images, videos, news, maps, music, IT, science, files, and social media
- **⏰ Time Filtering**: Filter results by day, week, month, or year
- **🔌 Easy Integration**: Seamless integration with Dify workflows
- **🐳 Docker Support**: Simple deployment using Docker containers

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
  - [Local Deployment with Docker](#local-deployment-with-docker)
  - [Using Existing SearXNG Instance](#using-existing-searxng-instance)
- [Usage](#usage)
- [Parameters](#parameters)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Prerequisites

Before installing and configuring the SearXNG plugin, ensure you have:

- **Dify Platform Access**: Either Dify Community Edition or Dify Cloud with tool configuration permissions
- **Docker Environment**: Docker installed and running (for local deployment)
- **Network Access**: Ability to access SearXNG instance (local or remote)
- **Administrative Rights**: Permission to install plugins in your Dify workspace

## Installation

### From Dify Marketplace

1. Navigate to the **Dify Marketplace** in your Dify dashboard
2. Search for "SearXNG" in the plugins section
3. Click **Install** to add the plugin to your workspace
4. The plugin will be available in your **Tools** section after installation

### Manual Installation

If installing manually, ensure all files are properly structured:
```
searxng/
├── main.py
├── manifest.yml
├── tools/
│   └── searxng_search.py
├── provider/
│   └── searxng.yaml
├── icon.svg
└── README.md
```

## Configuration

### Local Deployment with Docker

#### Step 1: Set Up SearXNG Container

Create a dedicated directory for your SearXNG instance:

```bash
# Create and navigate to instance directory
mkdir my-searxng-instance && cd my-searxng-instance

# Set environment variables
export PORT=8081  # Using 8081 to avoid conflicts with other services
export INSTANCE_NAME="dify-searxng"

# Pull and run SearXNG container
docker pull searxng/searxng:latest

docker run --rm \
  -d \
  -p ${PORT}:8080 \
  -v "${PWD}/searxng:/etc/searxng" \
  -e "BASE_URL=http://localhost:${PORT}/" \
  -e "INSTANCE_NAME=${INSTANCE_NAME}" \
  --name searxng-dify \
  searxng/searxng:latest
```

#### Step 2: Configure SearXNG Settings

After the container starts, SearXNG will create a configuration directory. You need to modify the settings:

```bash
# Wait for configuration files to be created
sleep 10

# Edit the settings file
nano searxng/settings.yml
```

In the `settings.yml` file, ensure these configurations:

```yaml
search:
  formats:
    - html
    - json  # This is crucial for API access

server:
  limiter: false  # Disable rate limiting for API usage
  
# Optional: Configure specific engines
engines:
  - name: google
    disabled: false
  - name: bing
    disabled: false
  # ... other engines
```

#### Step 3: Restart and Verify

```bash
# Restart the container to apply changes
docker restart searxng-dify

# Verify the service is running
curl "http://localhost:8081/search?q=test&format=json"
```

### Using Existing SearXNG Instance

If you have access to an existing SearXNG deployment:

1. **Obtain the Base URL**: Get the full URL of your SearXNG instance (e.g., `https://searx.example.com`)
2. **Verify JSON Support**: Ensure the instance supports JSON format by testing:
   ```bash
   curl "https://your-searx-instance.com/search?q=test&format=json"
   ```
3. **Check Rate Limiting**: Confirm that API rate limiting allows your usage patterns

### Dify Integration

1. **Navigate to Tools**: In your Dify dashboard, go to **Tools** → **SearXNG** → **To Authorize**
2. **Enter Configuration**:
   - **Base URL**: Enter your SearXNG instance URL
     - For local Docker: `http://host.docker.internal:8081`
     - For remote instance: `https://your-searx-instance.com`
   - **Test Connection**: Click "Test" to verify connectivity
3. **Save Settings**: Click "Save" to complete the configuration

## Usage

### In Dify Workflows

Once configured, you can use SearXNG in your Dify workflows:

1. **Add Tool Node**: In your workflow, add a "Tool" node
2. **Select SearXNG**: Choose "SearXNG Search" from the available tools
3. **Configure Parameters**:
   - **Query**: Enter your search terms
   - **Search Type**: Select the type of content to search for
   - **Time Range**: Optionally filter by time period
4. **Connect Output**: Use the search results in subsequent workflow steps

### Example Workflow Usage

```python
# Example of using SearXNG results in a workflow
search_results = searxng_tool.invoke({
    "query": "artificial intelligence trends 2024",
    "search_type": "news",
    "time_range": "month"
})

# Process results
for result in search_results:
    print(f"Title: {result['title']}")
    print(f"URL: {result['url']}")
    print(f"Content: {result['content'][:200]}...")
```

## Parameters

### Required Parameters

| Parameter | Type | Description | Example |
|-----------|------|-------------|---------|
| `query` | string | Search keywords or phrase | "machine learning python" |

### Optional Parameters

| Parameter | Type | Default | Description | Options |
|-----------|------|---------|-------------|---------|
| `search_type` | select | "general" | Type of content to search | general, images, videos, news, map, music, it, science, files, social_media |
| `time_range` | select | null | Time period for results | day, week, month, year |

### Search Types Explained

- **General**: Web pages and general content
- **Images**: Image files and galleries
- **Videos**: Video content from various platforms
- **News**: News articles and current events
- **Map**: Geographic and location-based results
- **Music**: Audio files and music-related content
- **IT**: Technology and programming resources
- **Science**: Scientific papers and research
- **Files**: Downloadable files and documents
- **Social Media**: Social network content

## Response Format

The plugin returns search results in JSON format:

```json
[
  {
    "title": "Result Title",
    "url": "https://example.com/page",
    "content": "Brief description of the content...",
    "engine": "google",
    "score": 0.95,
    "category": "general"
  }
]
```

## Troubleshooting

### Common Issues

#### 1. Connection Errors
**Problem**: "SearXNG api is required" or connection timeout
**Solutions**:
- Check if the SearXNG service is running: `docker ps | grep searxng`
- Verify the base URL is correct and accessible
- Ensure port 8081 is not blocked by firewall
- For Docker Desktop users, use `host.docker.internal` instead of `localhost`

#### 2. JSON Format Not Supported
**Problem**: Results return HTML instead of JSON
**Solutions**:
- Verify `formats: [html, json]` in `settings.yml`
- Restart the SearXNG container after configuration changes
- Test JSON endpoint directly: `curl "http://localhost:8081/search?q=test&format=json"`

#### 3. Rate Limiting Issues
**Problem**: Requests are being rate-limited
**Solutions**:
- Set `limiter: false` in SearXNG configuration
- Implement request throttling in your workflow
- Consider using multiple SearXNG instances for high-volume usage

#### 4. Empty Results
**Problem**: "No results found" message
**Solutions**:
- Try different search terms or less specific queries
- Check if the selected search engines are working
- Verify the search category is appropriate for your query
- Test the same query directly on SearXNG web interface

### Debugging Steps

1. **Check Service Status**:
   ```bash
   docker logs searxng-dify
   ```

2. **Test API Directly**:
   ```bash
   curl -v "http://localhost:8081/search?q=test&format=json&categories=general"
   ```

3. **Verify Configuration**:
   ```bash
   cat searxng/settings.yml | grep -A5 -B5 "formats\|limiter"
   ```

4. **Network Connectivity**:
   ```bash
   ping host.docker.internal  # For Docker Desktop
   telnet localhost 8081      # Test port accessibility
   ```

## Performance Optimization

### For High-Volume Usage

- **Resource Allocation**: Increase Docker container memory and CPU limits
- **Multiple Instances**: Deploy multiple SearXNG instances behind a load balancer
- **Caching**: Implement result caching to reduce redundant searches
- **Request Batching**: Group similar queries when possible

### Configuration Tuning

```yaml
# In settings.yml
server:
  limiter: false
  image_proxy: true
  
search:
  safe_search: 0  # 0=off, 1=moderate, 2=strict
  autocomplete: ""
  default_lang: "en"
  
# Engine-specific optimizations
engines:
  - name: google
    timeout: 10.0
    disabled: false
  - name: bing
    timeout: 8.0
    disabled: false
```

## Security Considerations

- **Network Security**: Ensure SearXNG instance is properly secured if exposed to internet
- **Rate Limiting**: Implement appropriate rate limiting to prevent abuse
- **Input Validation**: Validate search queries to prevent injection attacks
- **Access Control**: Restrict access to SearXNG configuration files
- **Updates**: Keep SearXNG container updated with latest security patches

## Contributing

We welcome contributions to improve the SearXNG plugin! Here's how you can help:

### Development Setup

1. **Fork the Repository**: Create your own fork of the plugin
2. **Clone Locally**: 
   ```bash
   git clone https://github.com/your-username/searxng-dify-plugin.git
   cd searxng-dify-plugin
   ```
3. **Set Up Environment**: 
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

### Making Changes

1. **Create Feature Branch**: `git checkout -b feature/your-feature-name`
2. **Make Your Changes**: Implement your improvements
3. **Test Thoroughly**: Verify your changes work with different SearXNG configurations
4. **Update Documentation**: Update README and code comments as needed
5. **Submit Pull Request**: Create a PR with detailed description of changes

### Reporting Issues

When reporting issues, please include:
- Dify version and environment details
- SearXNG version and configuration
- Complete error messages and logs
- Steps to reproduce the issue
- Expected vs actual behavior

## License

This plugin is released under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.

## Support

- **Documentation**: Check this README for common issues and solutions
- **Community**: Join the Dify community forums for discussions
- **Issues**: Report bugs and request features via GitHub issues
- **SearXNG Documentation**: Visit [SearXNG docs](https://docs.searxng.org/) for engine-specific information

---

**Maintainer**: Junytang  
**Plugin Version**: 0.0.5  
**Dify Compatibility**: Community Edition & Cloud  
**Last Updated**: May 2025
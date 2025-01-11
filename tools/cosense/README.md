# Cosense Search Plugin for Dify

![Cosense Banner](./_assets/cosense-banner.png)

A Dify plugin that enables seamless integration with Cosense's knowledge search capabilities.

## Features

- Search across Cosense projects directly from Dify
- Access both public and private knowledge bases
- Get structured search results with titles and content
- Multilingual support (English/Japanese interface)

## Installation

1. Install the plugin through Dify Marketplace
2. Configure your project settings:
   - Project Name: The name of your Cosense project
   - Search Query: What you want to search for

### Authentication

This plugin supports both public and private Cosense projects:

- **Public Projects**: No authentication required. You can start searching immediately.
- **Private Projects**: Requires authentication via `connect.sid`:
  1. Log in to your Cosense account in your browser
  2. Access your browser's developer tools (usually F12)
  3. Go to the Application/Storage tab
  4. Find the `connect.sid` cookie under Cookies > scrapbox.io
  5. Copy the cookie value and use it for authentication

Note: The `connect.sid` value is only required when accessing private projects.

## Usage Examples

The plugin accepts simple search parameters:

```json
{
  "project_name": "your-project",
  "query": "your search terms"
}
```

Example response:

```json
{
    "query": "API documentation",
    "project": "help-jp",
    "results": {
        "pages": [
            {"title": "REST API Guide", ...},
            {"title": "API Examples", ...}
        ]
    },
    "result_count": 2
}
```

## About Cosense

[Cosense](https://cosen.se/product) is a cutting-edge knowledge management and collaboration platform designed for modern teams. Built on top of Scrapbox.io, it offers:

- **Real-time Collaboration**: Multiple team members can edit and contribute simultaneously
- **Flexible Organization**: Free-form linking and tagging for organic knowledge structure
- **Smart Search**: Advanced search capabilities with context-aware results
- **API Integration**: Rich API support for seamless integration with other tools
- **Enterprise Features**: SSO, access controls, and security features for business use

Cosense transforms how teams:
- Share and discover knowledge
- Document processes and decisions
- Collaborate on projects and research
- Build internal wikis and documentation

Visit [Cosense Product Page](https://cosen.se/product) to learn more about its features and capabilities.

Built with ❤️ for the Cosense community

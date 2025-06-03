# HubSpot Plugin for Dify

This plugin integrates HubSpot's CRM capabilities with Dify, allowing you to access and manage your HubSpot data directly from your Dify applications, enabling powerful automation and AI-assisted CRM workflows.

## Features

- **Get Companies**: Retrieve company data from your HubSpot CRM including names, domains, contact information, and more
- **Authentication**: Secure connection to HubSpot using API access tokens
- **Structured Data**: All API responses are properly formatted for use in your AI applications

## Installation

1. Install the plugin through Dify's Plugin Marketplace
2. Configure the plugin with your HubSpot API access token

## Authentication

You'll need a **HubSpot API access token** to use this plugin:

1. Log in to your HubSpot account at [https://app.hubspot.com/](https://app.hubspot.com/)
2. Navigate to Settings > Integrations > Private Apps
3. Click "Create private app"
4. Set up your app:
   - Name your app (e.g., "Dify Integration")
   - Add a description (optional)
   - Set the required scopes (start with read-only scopes like `crm.objects.companies.read`)
5. Click "Create app"
6. Copy the generated access token immediately (it won't be shown again)

**Important**: Your API token grants access to your HubSpot account. Keep it secure and never share it publicly. Consider starting with read-only scopes and only add write permissions if necessary.

## Usage

The plugin provides the following tools that can be used in your Dify applications:

### Get Companies

Retrieves a list of companies from your HubSpot CRM including company name, domain, contact information, and other properties.

Required parameters:
- None

Optional parameters:
- `limit`: Maximum number of companies to return (default: 10, max: 100)

Example:
```
Show me the top 5 companies from our HubSpot CRM.
```

Response includes:
- Company name
- Domain/website
- Location details (address, city, state, country)
- Contact information (phone)
- Industry type
- Creation and last updated dates

## Troubleshooting

If you encounter issues with the plugin:

1. **Authentication Errors**
   - Verify your API token is valid and has not expired
   - Check that your private app has the necessary scopes (`crm.objects.companies.read`, etc.)
   - Ensure your HubSpot account is active

2. **No Data Returned**
   - Confirm you have companies in your HubSpot account
   - Try increasing the limit parameter
   - Check your HubSpot permissions if you're not getting expected results

3. **Rate Limiting**
   - HubSpot has API rate limits that may affect the plugin's performance
   - If experiencing issues, try reducing the frequency of requests

## License

[License information]




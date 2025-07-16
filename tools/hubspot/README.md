# HubSpot Plugin for Dify

This plugin integrates HubSpot's CRM capabilities with Dify, allowing you to access and manage your HubSpot data directly from your Dify applications, enabling powerful automation and AI-assisted CRM workflows.

## Features

- **Get Companies**: Retrieve company data from your HubSpot CRM including names, domains, contact information, and more
- **Create Contact**: Create new contacts in your HubSpot CRM with comprehensive contact information
- **Authentication**: Secure connection to HubSpot using API access tokens
- **Structured Data**: All API responses are properly formatted for use in your AI applications

## Installation

1. Install the plugin through Dify's Plugin Marketplace
2. Configure the plugin with your HubSpot API access token

## Required Permissions

This plugin requires specific HubSpot API permissions (scopes) to function properly. You must grant these permissions when creating your HubSpot Private App:

### Minimum Required Scopes

| Scope | Purpose | Required For |
|-------|---------|--------------|
| `crm.objects.companies.read` | Read company data from HubSpot CRM | Get Companies tool |
| `crm.objects.contacts.read` | Read contact data from HubSpot CRM | Contact operations |
| `crm.objects.contacts.write` | Create and modify contacts in HubSpot CRM | Create Contact tool |

### Permission Details

- **For basic functionality**: You need at least `crm.objects.companies.read` to use the Get Companies feature
- **For contact creation**: You need both `crm.objects.contacts.read` and `crm.objects.contacts.write` 
- **Security best practice**: Start with read-only permissions and add write permissions only when needed

⚠️ **Important**: Without the proper scopes, the plugin will return authentication errors. Make sure to enable all required permissions when setting up your HubSpot Private App.

## Authentication

You'll need a **HubSpot API access token** to use this plugin:

1. Log in to your HubSpot account at [https://app.hubspot.com/](https://app.hubspot.com/)
2. Navigate to Settings > Integrations > Private Apps
3. Click "Create private app"
4. Set up your app:
   - Name your app (e.g., "Dify Integration")
   - Add a description (optional)
   - Set the required scopes:
     - `crm.objects.companies.read` - For reading company data
     - `crm.objects.contacts.read` - For reading contact data
     - `crm.objects.contacts.write` - For creating new contacts
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

### Create Contact

Creates a new contact in your HubSpot CRM with the provided information.

Required parameters:
- `email`: Contact's email address (serves as unique identifier)

Optional parameters:
- `firstname`: Contact's first name
- `lastname`: Contact's last name
- `phone`: Contact's phone number
- `company`: Contact's company name
- `jobtitle`: Contact's job title

Example:
```
Create a new contact for John Doe with email john.doe@example.com, phone number +1-555-0123, and company Acme Corp.
```

Response includes:
- Contact ID
- All provided contact information
- Creation timestamp
- Success confirmation

## Troubleshooting

If you encounter issues with the plugin:

1. **Authentication Errors**
   - Verify your API token is valid and has not expired
   - Check that your private app has the necessary scopes (`crm.objects.companies.read`, `crm.objects.contacts.read`, `crm.objects.contacts.write`)
   - Ensure your HubSpot account is active

2. **No Data Returned**
   - Confirm you have companies/contacts in your HubSpot account
   - Try increasing the limit parameter for company queries
   - Check your HubSpot permissions if you're not getting expected results

3. **Contact Creation Issues**
   - Ensure the email address is valid and unique
   - Verify you have write permissions (`crm.objects.contacts.write`) enabled
   - Check if a contact with the same email already exists

4. **Rate Limiting**
   - HubSpot has API rate limits that may affect the plugin's performance
   - If experiencing issues, try reducing the frequency of requests

## License

[License information]




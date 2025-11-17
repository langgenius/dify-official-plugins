# Privacy Policy

**Last Updated:** November 3, 2025

## Overview

This Salesforce Plugin for Dify ("the Plugin") is designed to integrate Salesforce CRM functionality into the Dify AI platform. This privacy policy outlines how the Plugin handles user data and credentials.

## Data Collection

### Credentials
The Plugin collects and stores the following Salesforce credentials:
- **Username**: Your Salesforce account email address
- **Password**: Your Salesforce account password
- **Security Token**: Your Salesforce security token
- **Domain** (optional): Environment identifier (production or sandbox)

These credentials are used solely for authenticating with Salesforce APIs and are stored securely within the Dify platform.

### Usage Data
The Plugin does not independently collect or store any usage data, logs, or analytics. All interactions are conducted through the Dify platform according to Dify's own privacy policies.

## Data Processing

### Authentication
- Credentials are used exclusively to establish secure connections with Salesforce APIs
- Authentication occurs in real-time when tools are invoked
- No credentials are transmitted to any third parties other than Salesforce

### API Interactions
The Plugin makes API calls to Salesforce to:
- Create and manage cases
- Post messages to Salesforce Chatter
- Query user and organizational data as needed for functionality

All data transmitted during these operations is handled according to Salesforce's security protocols.

## Data Storage

- **Credentials**: Stored encrypted within the Dify platform's secure credential storage
- **No Local Storage**: The Plugin does not maintain local copies of any Salesforce data
- **No Caching**: API responses are not cached or persisted by the Plugin
- **Temporary Processing**: Data is only held in memory during active operations

## Third-Party Services

### Salesforce
This Plugin connects to Salesforce (salesforce.com) using official APIs. Salesforce's own privacy policy governs how your data is handled within their platform:
- Salesforce Privacy Policy: https://www.salesforce.com/company/privacy/

### simple-salesforce Library
The Plugin uses the open-source `simple-salesforce` Python library (version 0.1.45) to facilitate API communications. This library is maintained by the Python community and does not collect any user data.

## Data Security

- All API communications use HTTPS/TLS encryption
- Credentials are never logged or exposed in error messages
- The Plugin follows Dify's security best practices for credential management
- Users are encouraged to use Salesforce's IP whitelisting features for additional security

## User Rights

### Access and Control
- Users maintain full control over their Salesforce credentials
- Credentials can be updated or removed at any time through the Dify interface
- Users can revoke access by changing their Salesforce password or security token

### Data Deletion
- Removing the Plugin configuration from Dify will delete stored credentials
- No data persists within the Plugin after removal
- Data within Salesforce must be managed according to Salesforce's data retention policies

## Compliance

### Salesforce Terms
Users are responsible for ensuring their use of this Plugin complies with:
- Salesforce's Terms of Service
- Their organization's Salesforce usage policies
- Any applicable data protection regulations (GDPR, CCPA, etc.)

### Organizational Policies
Organizations should:
- Review the Plugin's functionality before deployment
- Ensure appropriate user permissions in Salesforce
- Monitor API usage within Salesforce limits
- Follow internal security and compliance procedures

## Data Retention

- **Credentials**: Retained only while the Plugin is configured and in use
- **API Data**: Not retained by the Plugin; subject to Salesforce's retention policies
- **Logs**: Any operational logs are managed by the Dify platform according to their policies

## Updates to This Policy

This privacy policy may be updated to reflect changes in the Plugin's functionality or legal requirements. Users will be notified of significant changes through the Dify platform.

## Contact Information

For questions or concerns about this privacy policy, please contact:
- **Plugin Author**: langgenius
- **Dify Platform Support**: Refer to Dify's official support channels
- **Salesforce Privacy**: privacy@salesforce.com

## Disclaimer

This Plugin is provided "as is" without warranties. Users are responsible for:
- Maintaining the security of their credentials
- Ensuring compliance with applicable regulations
- Understanding how their data is used within Salesforce
- Following their organization's security policies

By using this Plugin, you acknowledge that you have read and understood this privacy policy and agree to its terms.
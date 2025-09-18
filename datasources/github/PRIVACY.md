# GitHub Datasource Plugin Privacy Policy

## Data Collection and Usage

### Information Collected
This plugin requires the following information to provide services:

#### Required Authentication Information
- **Personal Access Token** or **OAuth Access Token**: Used to authenticate with GitHub API
- **User Login**: GitHub username for identification

#### Optional Configuration Information
- OAuth client credentials (stored in system configuration only)

### Purpose of Information Usage
The collected information is only used for:
- Authenticating with GitHub API
- Accessing authorized repositories, issues, and pull requests
- Retrieving file content and metadata
- Providing datasource service functionality

## Data Access Scope

### Content We Access
- Repository information and metadata
- File content from authorized repositories
- Issue and pull request content and comments
- User profile information (name, avatar, login)
- Repository activity and statistics

### Content We Do Not Access
- Private repositories without explicit authorization
- Other users' private data
- GitHub system administration data
- Billing or payment information

## Data Storage and Security

### Local Storage
- Authentication tokens are securely encrypted and stored in the Dify platform
- No repository content is permanently stored
- Only necessary metadata is temporarily cached

### Transmission Security
- All communications with GitHub use HTTPS encryption
- Follows GitHub's API security standards
- Respects GitHub's rate limiting and usage policies

### Access Control
- Only authorized Dify users can access configured datasources
- Token permissions are limited to explicitly granted scopes
- Follows the principle of least privilege

## Third-Party Services

### GitHub
- This plugin communicates directly with GitHub's REST API
- Follows GitHub's Terms of Service and Privacy Policy
- GitHub Privacy Policy: https://docs.github.com/en/site-policy/privacy-policies/github-privacy-statement

### Data Location
- Data remains within GitHub's infrastructure
- No data transfer to unauthorized third parties
- Follows GitHub's data residency policies

## User Rights

### Data Control
- You retain full control over all data in your GitHub repositories
- Can revoke plugin access permissions at any time
- Can delete or modify stored authentication information

### Access and Deletion
- Can view the scope of data accessed by the plugin
- Can disable or delete datasource configuration at any time
- Deleting configuration will clear all related authentication information

## Security Best Practices

### Token Security
- Use Personal Access Tokens with minimal required scopes
- Regularly rotate access tokens
- Monitor token usage in GitHub settings
- Revoke unused or suspicious tokens

### Permission Management
- Grant only necessary repository access permissions
- Use fine-grained personal access tokens when available
- Regularly review granted permissions
- Monitor access logs in GitHub audit trail

## Rate Limiting and Usage

### API Usage
- Respects GitHub API rate limits
- Implements automatic retry with backoff
- Does not abuse GitHub's infrastructure
- Follows GitHub's API usage guidelines

### Monitoring
- Tracks API usage to prevent rate limit violations
- Logs access patterns for debugging purposes
- Alerts users when rate limits are approached

## Compliance

### Data Protection Regulations
- Supports GDPR compliance for EU users
- Follows applicable data protection laws
- Supports data subject rights requests

### Industry Standards
- Follows industry security best practices
- Implements secure coding standards
- Regular security reviews and updates

## Incident Response

### Security Incidents
If security incidents are discovered, we will:
- Immediately investigate and assess impact
- Promptly notify affected users
- Take measures to prevent further data exposure
- Cooperate with GitHub for investigation if needed

### Token Compromise
If token compromise is detected:
- Immediately revoke affected tokens
- Notify users to regenerate tokens
- Review access logs for unauthorized activity
- Update security measures as needed

## Contact Information

### Privacy Issues
For privacy-related questions, please contact:
- Email: privacy@dify.ai
- Address: Dify Data Protection Officer

### Technical Support
For technical issues, please contact:
- Email: support@dify.ai
- Documentation: https://docs.dify.ai

## Policy Updates

### Update Notifications
- Privacy policy changes will be notified to users in advance
- Major changes require explicit user consent
- Update history is maintained in this document

### Version History
- **v1.0** (2025-01-27): Initial comprehensive privacy policy
- Complete GitHub API integration privacy protection
- Clear scope of data collection and usage

---

Last Updated: January 27, 2025  
Version: 1.0
# OneDrive Datasource Plugin Privacy Policy

## Data Collection and Usage

### Information Collected
This plugin requires the following information to provide services:

#### Required Authentication Information
- **OAuth Access Token**: Used to authenticate with Microsoft Graph API
- **OAuth Refresh Token**: Used to maintain access without re-authorization
- **User Email**: Microsoft account email for identification

#### Automatically Collected Information
- **User Profile**: Display name and user principal name from Microsoft Graph
- **File Metadata**: File names, sizes, modification dates, and folder structure
- **OneDrive Structure**: Folder hierarchy and file organization

### Purpose of Information Usage
The collected information is only used for:
- Authenticating with Microsoft Graph API and OneDrive
- Browsing and accessing authorized OneDrive files and folders
- Retrieving file content and metadata for datasource functionality
- Maintaining authenticated sessions through token refresh

## Data Access Scope

### Content We Access
- OneDrive file and folder listings
- File content from authorized OneDrive storage
- User profile information (name, email)
- File metadata (size, modification date, type)
- Folder structure and organization

### Content We Do Not Access
- Files from unauthorized OneDrive accounts
- Microsoft system administration data
- Other Microsoft 365 services beyond OneDrive
- Billing or subscription information
- Email content from Outlook or other services

## Data Storage and Security

### Local Storage
- OAuth tokens are securely encrypted and stored in the Dify platform
- No file content is permanently stored locally
- Only necessary metadata is temporarily cached for performance
- Authentication credentials are handled according to OAuth 2.0 security standards

### Transmission Security
- All communications with Microsoft Graph API use HTTPS encryption
- Follows Microsoft's API security standards and best practices
- OAuth tokens are transmitted securely using industry-standard protocols
- Respects Microsoft Graph API rate limiting and usage policies

### Access Control
- Only authorized Dify users can access configured OneDrive datasources
- Token permissions are limited to explicitly granted scopes
- Follows the principle of least privilege
- Supports Microsoft's conditional access policies

## Third-Party Services

### Microsoft Graph API
- This plugin communicates directly with Microsoft Graph API
- Follows Microsoft's Terms of Service and Privacy Policy
- Microsoft Privacy Policy: https://privacy.microsoft.com/privacystatement
- Graph API Documentation: https://docs.microsoft.com/en-us/graph/

### Data Location
- Data remains within Microsoft's cloud infrastructure
- Follows Microsoft's data residency and sovereignty policies
- No data transfer to unauthorized third parties
- Complies with Microsoft's regional data center policies

## OAuth Scopes and Permissions

### Required Scopes
- `offline_access`: Maintain access through refresh tokens
- `User.Read`: Read basic user profile information
- `Files.Read`: Read user's files in OneDrive
- `Files.Read.All`: Read all files that user can access

### Permission Justification
- **offline_access**: Required for seamless token refresh without user intervention
- **User.Read**: Needed for user identification and authentication validation
- **Files.Read**: Essential for accessing and retrieving OneDrive file content
- **Files.Read.All**: Enables access to shared files and collaborative content

## Data Retention and Deletion

### Token Storage
- Access tokens are stored until expiration or user revocation
- Refresh tokens are stored to maintain seamless access
- Tokens are automatically purged when datasource is deleted
- Emergency token revocation is supported

### Content Caching
- File metadata may be cached temporarily for performance optimization
- Cache is cleared regularly and upon datasource deletion
- No file content is stored permanently
- Cache respects Microsoft's data handling requirements

### User-Initiated Deletion
- Users can delete datasource configuration at any time
- All stored credentials and cached data are immediately removed
- Deletion is irreversible and complete
- Users can revoke access through Microsoft account settings

## User Rights and Control

### Data Control
- Users retain full ownership of all OneDrive data
- Can revoke plugin access at any time through Microsoft account settings
- Can delete datasource configuration from Dify platform
- Full control over which files and folders are accessible

### Access Management
- Can modify permissions through Microsoft's admin portal
- Can monitor access through Microsoft's audit logs
- Can review app permissions in Microsoft account security settings
- Can report security concerns through Microsoft's channels

### Transparency
- Full visibility into what data is accessed and when
- Clear documentation of all required permissions
- Regular updates on data handling practices
- Open communication about privacy and security measures

## Compliance and Standards

### Data Protection Regulations
- Supports GDPR compliance for EU users
- Follows applicable data protection laws globally
- Supports data subject rights requests
- Implements privacy by design principles

### Industry Standards
- Follows OAuth 2.0 security specifications
- Implements Microsoft's recommended security practices
- Complies with enterprise security requirements
- Regular security audits and updates

### Microsoft Compliance
- Leverages Microsoft's enterprise-grade compliance
- Benefits from Microsoft's certifications (SOC, ISO, etc.)
- Follows Microsoft's data governance frameworks
- Aligns with Microsoft 365 compliance features

## Security Measures

### Token Security
- Secure storage using Dify's encrypted credential management
- Automatic token rotation through refresh mechanism
- Protection against token interception and replay attacks
- Secure transmission using HTTPS and OAuth 2.0 standards

### API Security
- Rate limiting to prevent abuse of Microsoft Graph API
- Error handling that doesn't expose sensitive information
- Secure error logging and monitoring
- Protection against common API vulnerabilities

### Access Monitoring
- Logging of datasource access patterns
- Monitoring for unusual or suspicious activity
- Integration with Microsoft's security monitoring
- Alerting for potential security issues

## Incident Response

### Security Incidents
If security incidents are discovered, we will:
- Immediately investigate and assess the scope of impact
- Notify affected users within required timeframes
- Coordinate with Microsoft if their services are involved
- Take measures to prevent further unauthorized access
- Provide clear guidance on remedial actions

### Token Compromise
If token compromise is detected:
- Immediately revoke affected tokens through Microsoft Graph
- Notify users to re-authorize through OAuth
- Review access logs for unauthorized activity
- Update security measures and monitoring

### Data Breach Response
In case of data breach:
- Immediate containment and impact assessment
- Notification to users and relevant authorities as required
- Coordination with Microsoft's security team if needed
- Comprehensive post-incident review and improvements

## Contact Information

### Privacy Inquiries
For privacy-related questions and requests:
- Email: privacy@dify.ai
- Subject: OneDrive Datasource Privacy Inquiry
- Contact: Dify Data Protection Officer

### Security Issues
For security concerns and incident reporting:
- Email: security@dify.ai
- Subject: OneDrive Datasource Security Issue
- Emergency: Use expedited security contact procedures

### Technical Support
For technical assistance and general questions:
- Email: support@dify.ai
- Documentation: https://docs.dify.ai
- Community: Dify community forums

## Policy Updates and Changes

### Update Notifications
- Users will be notified of privacy policy changes in advance
- Material changes require explicit user consent
- Update history is maintained in this document
- Changes are communicated through multiple channels

### Review Schedule
- Annual review of privacy practices and policies
- Updates following significant feature changes
- Regular alignment with evolving regulations
- Continuous improvement based on user feedback

### Version History
- **v1.0** (2025-01-27): Initial comprehensive privacy policy
- Complete Microsoft Graph API integration privacy protection
- Clear documentation of data flows and security measures
- Comprehensive user rights and control mechanisms

---

**Last Updated**: January 27, 2025  
**Version**: 1.0  
**Next Review**: January 27, 2026

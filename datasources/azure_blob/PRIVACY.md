# Azure Blob Storage Datasource Plugin Privacy Policy

## Data Collection and Usage

### Information Collected
This plugin requires the following information to provide services:

#### Required Authentication Information
- **Storage Account Name**: Used to identify your Azure storage account
- **Authentication Credentials** (one of the following):
  - Account access key
  - SAS (Shared Access Signature) token
  - Connection string
- **Endpoint Configuration**: Cloud environment endpoint suffix

#### Optional Configuration Information
- Default container name
- Custom endpoint settings

### Purpose of Information Usage
The collected information is only used for:
- Establishing secure connections to your Azure Blob Storage
- Verifying access permissions
- Browsing and retrieving stored file content
- Providing datasource service functionality

## Data Storage and Security

### Local Storage
- Authentication credentials are securely encrypted and stored in the Dify platform
- Your actual file content is not stored
- Only necessary metadata information is cached

### Transmission Security
- All communications with Azure use HTTPS encryption
- Supports Azure enterprise-grade security standards
- Follows Azure data transmission best practices

### Access Control
- Only authorized Dify users can access configured datasources
- Supports role-based access control
- Follows the principle of least privilege

## Data Access Scope

### Content We Access
- Storage container lists
- Blob file lists and metadata
- File content (only when explicitly requested)
- Basic storage account information

### Content We Do Not Access
- Unauthorized containers or files
- Storage accounts outside the configured scope
- Any personal identification information (unless stored in files)

## Third-Party Services

### Microsoft Azure
- This plugin communicates directly with Microsoft Azure Blob Storage service
- Follows Microsoft Azure's terms of service and privacy policy
- Azure privacy policy: https://privacy.microsoft.com/privacystatement

### Data Location
- Data remains within your selected Azure region
- No data transfer to other geographic locations
- Follows Azure data residency policies

## User Rights

### Data Control
- You retain full control over all data stored in Azure Blob Storage
- Can revoke plugin access permissions at any time
- Can delete or modify stored authentication information

### Access and Deletion
- Can view the scope of data accessed by the plugin
- Can disable or delete datasource configuration at any time
- Deleting configuration will clear all related authentication information

## Compliance

### Data Protection Regulations
- Supports GDPR (General Data Protection Regulation) compliance
- Follows applicable data protection laws
- Supports data subject rights requests

### Industry Standards
- Follows ISO 27001 information security management standards
- Meets SOC 2 Type II control requirements
- Supports Azure compliance certifications

## Security Best Practices

### Authentication Security
- Use SAS tokens instead of account keys (recommended)
- Set appropriate token expiration times
- Regularly rotate access credentials
- Enable access logs and monitoring

### Permission Management
- Grant only necessary read and list permissions
- Avoid using overly broad permissions
- Regularly audit access permissions
- Use Azure RBAC for fine-grained control

### Monitoring and Auditing
- Enable Azure storage account logs
- Monitor abnormal access patterns
- Set security alerts
- Regularly check access logs

## Incident Response

### Security Incidents
If security incidents are discovered, we will:
- Immediately investigate and assess impact
- Promptly notify affected users
- Take measures to prevent further data exposure
- Cooperate with relevant authorities for investigation

### Data Breach Notification
- Notify within 72 hours of discovering a data breach
- Provide incident details and impact assessment
- Explain remedial measures taken
- Provide protection recommendations

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
- **v1.0** (2025-01-27): Initial version
- Privacy protection support for three authentication methods
- Clear scope of data collection and usage

---

Last Updated: January 27, 2025  
Version: 1.0




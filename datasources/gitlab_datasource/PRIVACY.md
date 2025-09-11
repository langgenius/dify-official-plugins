# GitLab Datasource Plugin - Privacy Policy

**Effective Date:** January 2025  
**Version:** 1.0  
**Plugin Version:** 0.3.0

## Overview

This privacy policy describes how the GitLab Datasource Plugin for Dify ("the Plugin") collects, uses, and protects your information when accessing GitLab projects, issues, merge requests, and files. We are committed to protecting your privacy and ensuring transparent data handling practices.

## 📊 Data Collection and Usage

### What Data We Access

The Plugin accesses only the GitLab data you explicitly authorize:

#### **Project Data**
- Project metadata (name, description, visibility, creation date)
- Repository structure and file listings
- File contents (code, documentation, configuration files)
- Branch and tag information
- Project settings and permissions

#### **Issue Data**
- Issue titles, descriptions, and metadata
- Issue comments and discussion threads
- Labels, assignees, and status information
- Creation and modification timestamps

#### **Merge Request Data**
- MR titles, descriptions, and metadata
- Discussion threads and review comments
- Code changes and diffs (when requested)
- Approval status and pipeline information

#### **User Data**
- GitLab username and display name
- User avatar URLs (for attribution)
- Email addresses (only if publicly available)
- User activity related to accessed content

### How We Use Your Data

Your GitLab data is used exclusively for:

1. **Knowledge Base Construction**: Processing and indexing content for Dify's AI capabilities
2. **Content Retrieval**: Providing access to your GitLab content within Dify workflows
3. **Metadata Enhancement**: Enriching content with context and relationships
4. **Search and Discovery**: Enabling intelligent search across your GitLab content

### What We Do NOT Do

- ❌ Store your GitLab credentials permanently
- ❌ Access content outside your explicit authorization
- ❌ Share your data with unauthorized third parties
- ❌ Use your data for advertising or marketing
- ❌ Perform analytics on your private content
- ❌ Modify or delete your GitLab content

## 🔐 Authentication and Credential Security

### Personal Access Tokens (PAT)

**Storage**: Personal Access Tokens are encrypted and stored securely within the Dify platform using industry-standard encryption methods.

**Transmission**: All token transmission occurs over HTTPS/TLS encrypted connections.

**Scope Limitation**: We recommend using tokens with minimal required scopes:
- `read_user`: User profile access
- `read_repository`: Project file access  
- `api`: Issues and merge request access

**Token Rotation**: We recommend rotating tokens every 90 days for enhanced security.

### OAuth 2.0 Authentication

**Authorization Flow**: Follows GitLab's standard OAuth 2.0 flow with PKCE (Proof Key for Code Exchange) when supported.

**Token Storage**: Access tokens are encrypted and stored securely. Refresh tokens are used to maintain authentication without requiring re-authorization.

**Scope Management**: OAuth applications request only the minimum necessary scopes for functionality.

## 🌐 GitLab Instance Types

### GitLab.com (Cloud)

When using GitLab.com:
- Data transmission follows GitLab's cloud infrastructure security
- Subject to GitLab's privacy policy and terms of service
- Geographic data location depends on GitLab's cloud regions

### Self-hosted GitLab Instances

For self-hosted installations:
- Data remains within your infrastructure
- Network communication occurs directly between Dify and your GitLab instance
- You maintain full control over data location and access
- Subject to your organization's security policies

## 🛡️ Data Security Measures

### Encryption

**In Transit**: All data transmission uses TLS 1.2+ encryption
**At Rest**: Credentials and cached data are encrypted using AES-256
**Key Management**: Encryption keys are managed through secure key management systems

### Access Controls

- Role-based access control (RBAC) for plugin configuration
- Audit logging of all data access activities
- Regular security assessments and updates
- Compliance with industry security standards

### Network Security

- HTTPS-only communications
- Certificate pinning for enhanced security
- Support for corporate proxy configurations
- IP whitelisting capabilities for enterprise deployments

## ⏱️ Data Retention and Caching

### Temporary Caching

**Purpose**: Improve performance and reduce GitLab API usage
**Duration**: Content cached for maximum 24 hours
**Scope**: Only explicitly requested content is cached
**Security**: Cached data is encrypted and automatically purged

### Credential Retention

**Access Tokens**: Stored until manually removed or expired
**OAuth Tokens**: Refreshed automatically; old tokens immediately invalidated
**User Data**: Retained only while plugin is actively configured

### Data Purging

- Automatic cleanup of expired cache data
- Manual data purging available through plugin settings
- Complete data removal upon plugin disconnection

## 👤 User Rights and Controls

### Access Control

You maintain full control over:
- Which GitLab projects the plugin can access
- Authentication method and credential management
- Data retention and caching preferences
- Plugin activation and deactivation

### Data Portability

- Export functionality for accessed content metadata
- Standard formats for data extraction
- No vendor lock-in; data remains in GitLab

### Right to Deletion

- Remove plugin authorization at any time
- Delete cached data through plugin interface
- Revoke GitLab tokens to immediately cut access

## 🔗 Third-Party Services

### GitLab Services

**API Usage**: Plugin interacts with GitLab APIs according to GitLab's terms of service
**Data Flow**: Data flows directly between Dify and GitLab; no intermediary services
**Privacy Policy**: Subject to GitLab's privacy policy for API usage

### Dify Platform

**Integration**: Plugin operates within Dify's security framework
**Data Handling**: Subject to Dify's privacy policy and security measures
**Isolation**: Plugin data is isolated from other Dify components

## 📋 Compliance and Legal

### Regulatory Compliance

- **GDPR**: Full compliance with European data protection regulations
- **CCPA**: Compliance with California Consumer Privacy Act
- **SOC 2**: Security controls aligned with SOC 2 Type II standards
- **HIPAA**: Available for healthcare deployments (enterprise)

### Data Processing Lawful Basis

- **Consent**: Explicit user consent for data access
- **Legitimate Interest**: Necessary for providing requested services
- **Contract**: Required for fulfilling service agreements

### International Transfers

- Data location depends on your Dify deployment region
- Standard contractual clauses for international transfers
- Compliance with applicable data transfer regulations

## 🚨 Incident Response

### Security Incidents

In case of a security incident:
1. **Immediate Response**: Automatic system isolation and investigation
2. **User Notification**: Prompt notification of affected users
3. **Remediation**: Swift action to address vulnerabilities
4. **Transparency**: Full incident reporting and lessons learned

### Data Breach Protocol

- **Detection**: Automated monitoring and alerting systems
- **Assessment**: Rapid impact assessment and classification
- **Notification**: Regulatory and user notifications within required timeframes
- **Recovery**: Comprehensive recovery and prevention measures

## 🏢 Enterprise and Self-Hosted Deployments

### Enterprise Features

- **SSO Integration**: Support for SAML and OAuth SSO providers
- **Advanced Audit Logging**: Comprehensive audit trails and reporting
- **Custom Security Policies**: Configurable security and privacy controls
- **Dedicated Support**: Priority support for privacy and security questions

### On-Premises Deployments

- **Data Sovereignty**: Complete data control within your infrastructure
- **Custom Compliance**: Tailored compliance for specific industry requirements
- **Network Isolation**: Air-gapped deployment options available
- **Local Authentication**: Integration with enterprise identity providers

## 📞 Contact and Support

### Privacy Questions

For privacy-related questions or concerns:

**Email**: privacy@dify.ai  
**Subject**: GitLab Plugin Privacy Inquiry  
**Response Time**: Within 48 hours for privacy concerns

### Data Subject Requests

To exercise your privacy rights:

**Email**: privacy@dify.ai  
**Include**: 
- Plugin name (GitLab Datasource)
- Request type (access, deletion, correction)
- Verification information

### Technical Support

For technical issues related to the plugin:

**Community Support**: [Dify Discord](https://discord.gg/dify)  
**Documentation**: [Plugin Documentation](https://docs.dify.ai/plugins)  
**Enterprise Support**: enterprise@dify.ai

## 📜 Policy Updates

### Notification of Changes

- **Major Changes**: 30-day advance notice via email and platform notifications
- **Minor Updates**: Notification through platform changelog
- **Emergency Changes**: Immediate notification for security-related updates

### Version History

- **v1.0** (January 2025): Initial comprehensive privacy policy
- Future updates will be tracked with version numbers and change descriptions

### Consent Management

- Continued use implies consent to updated policies
- Option to withdraw consent and discontinue plugin use
- Clear notification of material changes requiring explicit consent

## 🎯 Best Practices for Users

### Securing Your GitLab Integration

1. **Use Minimal Scopes**: Grant only necessary permissions
2. **Regular Token Rotation**: Update tokens quarterly
3. **Monitor Access**: Review GitLab audit logs regularly
4. **Network Security**: Use HTTPS and secure network connections
5. **Review Permissions**: Periodically audit plugin access

### Data Minimization

- Configure plugin to access only required projects
- Use project-specific tokens when possible
- Regularly review and clean up unused integrations
- Consider separate tokens for different use cases

---

## Legal Notice

This privacy policy is governed by the laws of [Jurisdiction] and is subject to Dify's main Terms of Service and Privacy Policy. For the most current version of this policy, please visit our documentation site.

**Last Updated**: January 2025  
**Next Review**: July 2025

---

*This privacy policy is designed to be transparent and comprehensive. If you have any questions or suggestions for improvement, please contact our privacy team.*


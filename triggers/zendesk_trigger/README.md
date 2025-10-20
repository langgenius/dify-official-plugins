# Zendesk Trigger Plugin for Dify

A comprehensive webhook-based trigger plugin for Zendesk that enables intelligent automation workflows in Dify.

## Overview

This plugin connects Zendesk's customer service platform with Dify's AI capabilities through webhook triggers. It supports various Zendesk events to enable intelligent customer service automation, and knowledge base optimization.

## Use Cases

### 1. Intelligent Ticket Processing
- **Scenario**: Automatically analyze new tickets and route them to the right agent
- **Trigger**: `ticket_created`
- **Workflow**:
  - AI analyzes ticket content, priority, and sentiment
  - Recommends best-fit agent based on expertise
  - Generates initial response suggestions

### 2. SLA Monitoring & Alerts
- **Scenario**: Prevent SLA breaches with proactive alerts
- **Trigger**: `ticket_status_changed`, `ticket_priority_changed`
- **Workflow**:
  - Monitor ticket status transitions
  - Alert when approaching SLA deadlines
  - Trigger automated escalation

### 3. Knowledge Base Optimization
- **Scenario**: Improve help center content based on ticket trends
- **Trigger**: `article_published`, `article_unpublished`
- **Workflow**:
  - Analyze common ticket topics
  - Recommend knowledge base articles
  - Optimize agent efficiency

## Supported Events

### Ticket Events
- **ticket_created**: New support ticket created
- **ticket_marked_as_spam**: Ticket flagged as spam by Zendesk
- **ticket_status_changed**: Ticket status changed (new → open → solved → closed)
- **ticket_priority_changed**: Ticket priority modified (low → urgent)
- **ticket_comment_created**: Comment added to ticket (public or private)

### Knowledge Base Events
- **article_published**: Help center article published
- **article_unpublished**: Help center article unpublished

## Configuration

### Prerequisites
1. Zendesk account with admin access
2. API Token from Zendesk Admin Center
3. Zendesk subdomain (e.g., `acme` for acme.zendesk.com)

### Setup Steps

1. **Get Zendesk API Credentials**
   - Navigate to Admin Center → Apps and integrations → APIs → Zendesk API
   - Generate a new API Token
   - Note your admin email address

2. **Install Plugin in Dify**
   - Upload plugin to Dify workspace
   - Configure credentials:
     - **Email**: Your Zendesk admin email
     - **API Token**: Generated API token
     - **Subdomain**: Your Zendesk subdomain

3. **Create Webhook Subscription**
   - Select events to monitor
   - (Optional) Set webhook secret for signature validation
   - Plugin automatically creates webhook in Zendesk

## Event Filtering

Each event type supports powerful filtering options:

### Ticket Filters
- **Status**: Filter by ticket status (new, open, pending, solved, closed)
- **Priority**: Filter by priority level (urgent, high, normal, low)
- **Tags**: Require specific tags
- **Type**: Filter by ticket type (problem, incident, question, task)
- **Subject/Description Contains**: Keyword matching

### Comment Filters
- **Public/Private**: Filter by comment visibility
- **Body Contains**: Keyword matching in comment text

### Article Filters
- **Locale**: Filter by language (en-us, ja, zh-cn, etc.)
- **Title Contains**: Keyword matching in article titles

## Troubleshooting

### Common Issues

**Webhook not receiving events**
- Verify webhook is active in Zendesk Admin
- Check Dify endpoint is publicly accessible
- Review Zendesk webhook delivery logs

**Events being filtered out**
- Check event filter parameters
- Review payload structure in Zendesk logs
- Test with minimal filters first


## Support

- **Documentation**: https://developer.zendesk.com/documentation/
- **Dify Plugin Docs**: https://docs.dify.ai/
- **Issues**: Report issues in the Dify Plugin SDK repository

## Version History

- **1.0.0** (2025-01-17): Initial release
  - Support for ticket, comment, rating, and article events
  - Comprehensive filtering options
  - Webhook signature validation
  - Multi-language support (EN, ZH, JA)

# outlook

Dify's integration with Microsoft Outlook that can help you read, send, list, delete Outlook Email.

## Features
- List Messages: List messages from your Outlook inbox.
- Get Message: Get detailed information about a specific email message by its ID.
- Send Message: Send a message through Outlook using Microsoft Graph API.
- Send Draft: Send a draft email message through Outlook using Microsoft Graph API, requires a draft ID from the draft_message tool.
- Draft Email: Create a draft email in Outlook.
- List Draft Emails: List your draft emails.
- Add Attachment to Draft: Add a file attachment to a draft email.
- Prioritize Email: Set the priority level of an email message.

## Setup
1. Install this plugin from the Dify Marketplace.
2. Open the plugin settings in Dify.
3. Save the configuration.

## Usage
Add the outlook tools to an agent or workflow, fill in the required inputs, and run the node to call the upstream service.

## Privacy
This plugin sends the inputs required by the selected operation to the upstream service. See [PRIVACY.md](PRIVACY.md) for details.

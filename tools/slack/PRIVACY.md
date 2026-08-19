# Privacy Policy

## Data Collection

This plugin does not collect or store any personal data on its own. To operate, it requires a Slack credential that you provide:

- A **Slack Bot User OAuth Token** (`xoxb-...`), or
- A **Slack Incoming Webhook URL**.

These credentials are stored and managed by your Dify instance and are used only to authenticate requests to Slack.

## Data Processing

When you invoke a tool, the parameters you supply (such as channel IDs, message text, timestamps, user IDs, emails, or file contents) are sent directly to the Slack Web API in order to perform the requested action. The plugin acts only as a pass-through between Dify and Slack and does not retain any of this data after a request completes.

## Third-party Services

This plugin communicates with **Slack** (https://slack.com). Your use of Slack is governed by Slack's Privacy Policy: https://slack.com/trust/privacy/privacy-policy

## Data Retention

The plugin itself retains no data. Credentials are retained by your Dify instance for as long as the plugin is configured. Any content sent to or retrieved from Slack is subject to Slack's own retention policies.

## User Rights

Because the plugin stores no data of its own, requests regarding data access, correction, or deletion should be directed to your Dify administrator (for stored credentials) and to Slack (for data held in your workspace).

## Contact Information

For privacy-related questions about this plugin, please contact the plugin author via the Dify Marketplace listing.

Last updated: 2025-07-31

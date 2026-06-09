# Privacy Policy — Resemble Detect + Intelligence (Dify plugin)

This plugin connects your Dify workflows to the Resemble AI Detect + Intelligence
API (`https://app.resemble.ai/api/v2`).

## What data is sent
- **Your Resemble API key**, supplied as a plugin credential, is sent as a Bearer
  token to authenticate requests to Resemble AI. It is stored by Dify's credential
  store and is never logged by this plugin.
- **Media URLs (and optional parameters)** you provide to the tools are sent to
  Resemble AI for analysis. Media must be hosted at a public HTTPS URL or supplied
  via a Resemble secure-upload token; this plugin does not upload local files.

## What data is processed
- Detection / intelligence / watermark results returned by Resemble AI are passed
  back into your Dify workflow. This plugin does not store, retain, or transmit
  results anywhere else.

## Data retention
- Resemble AI processes and may store submitted media per its own policy. To have
  media auto-deleted after analysis, enable the **Zero-Retention Mode** toggle on the
  Deepfake Detection tool.

## Third parties
- The only third party is **Resemble AI**. See https://www.resemble.ai/privacy/ for
  Resemble's data handling. This plugin sends no data to any other party.

## Contact
For questions about this plugin's data handling, contact the plugin author.

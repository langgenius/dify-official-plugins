# Privacy Policy

This Privacy Policy explains how we collect, use, and protect your information when you use the Google Cloud Storage Datasource Plugin for Dify.

## Information Collection

We do not collect, store, or share any personal information from users. All data processed by the plugin is handled locally or through secure connections to Google Cloud Storage services, as required for functionality.

## Use of Information

The plugin only accesses your Google Cloud Storage buckets and objects to provide the requested features, such as browsing and downloading files from your storage buckets. No data is stored or transmitted to third parties by the plugin itself.

## Data Security

We are committed to ensuring the security of your data. All communications with Google Cloud Storage services use secure protocols (HTTPS) and service account authentication. We do not retain any user credentials or file data beyond the duration of your session.

## Third-Party Services

This plugin interacts with Google Cloud Storage via official Google Cloud SDK. Please refer to Google Cloud's privacy policy for details on how your data is handled by Google Cloud services:
- [Google Cloud Privacy Policy](https://cloud.google.com/terms/privacy)
- [Google Cloud Storage Terms of Service](https://cloud.google.com/storage/terms)

## Data Access Scope

The plugin requires the following permissions to function:
- Storage Object Viewer (`storage.objects.list`, `storage.objects.get`): To list and download objects from buckets
- Storage Legacy Bucket Reader (`storage.buckets.list`, `storage.buckets.get`): To list and access bucket metadata

These permissions are granted through the service account credentials and are used solely for the intended functionality.

## Service Account Authentication

This plugin uses service account authentication:
- Service account credentials are provided as a JSON key file
- The credentials include project ID, private key, and client information
- These credentials are used only to authenticate with Google Cloud Storage
- Credentials are never stored permanently by the plugin
- The private key is transmitted securely and used only during active sessions

## Data Processing

When using this plugin:
- Bucket and file metadata (names, sizes, types) is retrieved to display file listings
- File content is downloaded only when explicitly requested by the user
- Files are accessed in read-only mode
- No files are modified, created, or deleted through this plugin
- All data transfers use Google Cloud's secure infrastructure

## User Rights

You have the right to:
- Control which service account credentials are used
- Limit the service account's permissions in Google Cloud IAM
- Revoke the service account's access at any time
- Monitor access logs in Google Cloud Console
- Request information about what data is accessed

## Compliance

This plugin respects:
- Google Cloud's data processing terms
- Regional data residency requirements (based on bucket location)
- Industry-standard security practices
- Your organization's data governance policies

## Changes to This Policy

We may update this Privacy Policy from time to time. Any changes will be posted in this document with an updated effective date.

## Contact

If you have any questions or concerns about this Privacy Policy, please contact the developer [hello@dify.ai](mailto:hello@dify.ai) or refer to the project repository for more information.

Last updated: December 2024

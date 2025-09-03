# Google Cloud Storage Datasource Plugin

**Author**: langgenius  
**Version**: 0.2.5  
**Type**: datasource

## Introduction

This plugin integrates with Google Cloud Storage (GCS), enabling automated access to your storage buckets and objects. It supports browsing buckets, navigating through folder hierarchies, and downloading files directly for use in platforms like Dify. The plugin uses service account authentication for secure, programmatic access to your GCS resources.

## Features

- **Browse Storage Buckets**: List all available GCS buckets in your project
- **Navigate Bucket Contents**: Browse through files and folders within buckets
- **Download Files**: Retrieve objects from GCS buckets for processing
- **Folder Navigation**: Support for hierarchical folder structure using prefixes
- **Pagination Support**: Efficiently handle buckets with large numbers of objects
- **Service Account Authentication**: Secure authentication using Google Cloud service accounts

## Setup

### Prerequisites

Before using this plugin, you need:
1. A Google Cloud Platform (GCP) account with an active project
2. Google Cloud Storage buckets with the files you want to access
3. A service account with appropriate permissions

### Configuration Steps

1. **Create a Google Cloud Project** (if not already exists):
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Click "Select a project" → "New Project"
   - Enter a project name and click "Create"

2. **Enable Google Cloud Storage API**:
   - In your GCP project, go to "APIs & Services" → "Library"
   - Search for "Cloud Storage API"
   - Click on it and press "Enable" (usually enabled by default)

3. **Create a Service Account**:
   - Navigate to "IAM & Admin" → "Service Accounts"
   - Click "Create Service Account"
   - Provide details:
     - **Name**: e.g., "dify-gcs-plugin"
     - **Description**: "Service account for Dify GCS plugin"
   - Click "Create and Continue"

4. **Grant Permissions**:
   - Assign one of these roles based on your needs:
     - **Storage Object Viewer**: Read-only access to objects
     - **Storage Legacy Bucket Reader**: Read access to buckets and objects
     - **Storage Admin**: Full control (only if write access is needed)
   - Or create a custom role with specific permissions:
     ```
     storage.buckets.list
     storage.buckets.get
     storage.objects.list
     storage.objects.get
     ```
   - Click "Continue" then "Done"

5. **Generate Service Account Key**:
   - Click on the created service account
   - Go to the "Keys" tab
   - Click "Add Key" → "Create new key"
   - Choose **JSON** as the key type
   - Click "Create"
   - A JSON file will be downloaded - **keep this secure**

6. **Configure the Plugin in Dify**:
   - Navigate to the datasource plugins section in Dify
   - Select Google Cloud Storage
   - In the **Credentials** field, paste the entire contents of the downloaded JSON key file
   - The JSON should contain:
     ```json
     {
       "type": "service_account",
       "project_id": "your-project-id",
       "private_key_id": "...",
       "private_key": "-----BEGIN PRIVATE KEY-----\n...",
       "client_email": "service-account@project.iam.gserviceaccount.com",
       "client_id": "...",
       "auth_uri": "https://accounts.google.com/o/oauth2/auth",
       "token_uri": "https://oauth2.googleapis.com/token",
       "auth_provider_x509_cert_url": "...",
       "client_x509_cert_url": "..."
     }
     ```
   - Click "Save" to store the credentials

## Usage

### Browsing Files

The plugin provides an online drive interface for browsing GCS content:

1. **List Buckets**: When no bucket is specified, the plugin lists all accessible buckets
2. **Browse Bucket Contents**: Select a bucket to view its files and folders
3. **Navigate Folders**: GCS uses prefixes to simulate folders - click to browse
4. **Pagination**: Use pagination controls for buckets with many objects

### Downloading Files

To download a file:
1. Browse to the desired file location
2. Select the file for download
3. The plugin retrieves the object content and metadata

## Supported Operations

| Operation | Description |
|-----------|-------------|
| List Buckets | View all GCS buckets in your project |
| Browse Objects | Navigate through files and folders in a bucket |
| Download Object | Retrieve object content from GCS |
| Pagination | Handle large object lists with page tokens |
| Prefix Filtering | Browse objects with specific prefixes (folders) |

## Bucket Organization

Google Cloud Storage uses a flat namespace with prefixes to simulate folders:
- Objects with `/` in their names appear as folders
- Example: `documents/2024/report.pdf` appears as nested folders
- The plugin automatically handles this structure for easy navigation

## Security Considerations

- **Service Account Keys**: Store your service account JSON key securely
- **Principle of Least Privilege**: Grant only necessary permissions to the service account
- **Key Rotation**: Regularly rotate service account keys for security
- **Audit Logging**: Enable Cloud Audit Logs to monitor access
- **Bucket Permissions**: Use IAM policies to control bucket-level access
- **Object Encryption**: GCS automatically encrypts data at rest

## Troubleshooting

### Common Issues

1. **"Credentials not found" error**:
   - Verify the JSON credentials are correctly pasted
   - Ensure the JSON is valid (no missing brackets or quotes)

2. **"Permission denied" error**:
   - Check the service account has necessary permissions
   - Verify the bucket exists and is accessible
   - Ensure the project ID in credentials is correct

3. **"Bucket not found" error**:
   - Verify the bucket name is correct
   - Check the bucket exists in the specified project
   - Ensure the service account has access to the bucket

4. **Authentication failures**:
   - Verify the service account is active
   - Check if the private key is valid
   - Ensure the service account hasn't been deleted

5. **Objects not showing**:
   - Check if objects exist with the specified prefix
   - Verify permissions include `storage.objects.list`
   - Ensure you're looking in the correct bucket

## Best Practices

1. **Service Account Management**:
   - Create dedicated service accounts for different applications
   - Use descriptive names for easy identification
   - Document which service accounts are used where

2. **Permission Management**:
   - Start with minimal permissions and add as needed
   - Use predefined roles when possible
   - Regularly audit service account permissions

3. **Security**:
   - Never commit service account keys to version control
   - Rotate keys periodically
   - Monitor service account usage in Cloud Console

4. **Performance**:
   - Use appropriate pagination sizes for large buckets
   - Consider bucket location for latency optimization
   - Use prefix filtering to reduce object listing overhead

## Pricing Considerations

Google Cloud Storage charges for:
- Storage (per GB per month)
- Network egress (data transfer out)
- Operations (Class A and Class B operations)

This plugin primarily performs:
- Class A operations: List buckets, list objects
- Class B operations: Get object (download)

For current pricing, see [GCS Pricing](https://cloud.google.com/storage/pricing).

## Regional Availability

GCS buckets can be created in different locations:
- **Multi-regions**: e.g., `us`, `eu`, `asia`
- **Dual-regions**: e.g., `nam4`, `eur4`
- **Single regions**: e.g., `us-east1`, `europe-west1`, `asia-southeast1`

Choose locations based on your data residency requirements and latency needs.

## Privacy

Please refer to the [Privacy Policy](PRIVACY.md) for information on how your data is handled when using this plugin.

## Support

For issues or questions:
- Contact: [hello@dify.ai](mailto:hello@dify.ai)
- Repository: Check the project repository for updates and documentation
- GCS Documentation: [https://cloud.google.com/storage/docs](https://cloud.google.com/storage/docs)

## Additional Resources

- [Google Cloud Storage Documentation](https://cloud.google.com/storage/docs)
- [Service Account Best Practices](https://cloud.google.com/iam/docs/best-practices-for-securing-service-accounts)
- [GCS Client Libraries](https://cloud.google.com/storage/docs/reference/libraries)
- [Google Cloud Console](https://console.cloud.google.com/)

Last updated: December 2024

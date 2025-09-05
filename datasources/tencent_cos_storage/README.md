# Tencent COS Storage Datasource Plugin

**Author**: langgenius  
**Version**: 0.0.1
**Type**: datasource

## Introduction

This plugin integrates with Tencent Cloud COS (Cloud Object Storage), enabling automated access to your COS buckets and objects. It supports browsing files and folders within COS buckets and downloading files directly for use in platforms like Dify.

## Features

- **Browse COS Buckets**: List all available COS buckets in your Tencent Cloud account
- **Browse Bucket Contents**: Navigate through folders and files within COS buckets
- **Download Files**: Retrieve files from COS buckets for processing
- **Folder Navigation**: Support for hierarchical folder structure browsing
- **Pagination Support**: Efficiently handle large numbers of files with pagination

## Setup

### Prerequisites

Before using this plugin, you need:
1. A Tencent Cloud account with active COS service
2. COS buckets with the files you want to access
3. Tencent Cloud CAM credentials with appropriate permissions

### Configuration Steps

1. **Create Tencent Cloud CAM User** (if not already exists):
   - Sign in to the [Tencent Cloud Console](https://console.cloud.tencent.com/)
   - Navigate to CAM (Cloud Access Management)
   - Click "Users" → "Create User"
   - Provide a user name (e.g., "dify-cos-plugin")
   - Select "Programmatic access" for Access type

2. **Set Permissions**:
   - [Attach policies that grant COS access](https://cloud.tencent.com/document/product/598/11084):
     - `QcloudCOSReadOnlyAccess` (for read-only access to all buckets)
     - Or create a custom policy with specific bucket permissions:
       ```json
            {
               "version": "2.0",
               "statement":[
                  {
                        "effect": "allow",
                        "action":  [
                                 "cos:List*",
                                 "cos:Get*",
                                 "cos:Head*",
                                 "cos:OptionsObject"
                              ],
                        "resource": "*"
                  }
               ]
            }
       ```

3. **Generate Access Keys**:
   - After creating the user, go to the "API Keys" tab
   - Click "Create Key"
   - Save the **SecretId** and **SecretKey** securely

4. **Configure the Plugin in Dify**:
   - **Secret ID**: Enter the SecretId from your Tencent Cloud CAM user
   - **Secret Key**: Enter the SecretKey from your Tencent Cloud CAM user
   - **Region**: Enter your COS region (e.g., `ap-beijing`, `ap-shanghai`, `ap-guangzhou`)
   - Click "Save" to store the credentials

## Usage

### Browsing Files

The plugin provides an online drive interface for browsing COS content:

1. **List Buckets**: When no bucket is specified, the plugin lists all available COS buckets
2. **Browse Bucket Contents**: Select a bucket to view its files and folders
3. **Navigate Folders**: Click on folders to browse their contents
4. **Pagination**: Use pagination controls for buckets with many files

### Downloading Files

To download a file:
1. Browse to the desired file
2. Select the file for download
3. The plugin retrieves the file content and metadata

## Supported Operations

| Operation | Description |
|-----------|-------------|
| List Buckets | View all COS buckets in your Tencent Cloud account |
| Browse Files | Navigate through files and folders in a bucket |
| Download File | Retrieve file content from COS |
| Pagination | Handle large file lists with continuation tokens |

## Security Considerations

- **Credentials**: Store your Tencent Cloud credentials securely and never share them
- **Permissions**: Use the principle of least privilege - grant only necessary COS permissions
- **Region**: Ensure you're using the correct Tencent Cloud region for your buckets
- **Encryption**: Consider using COS server-side encryption for sensitive data

## Troubleshooting

### Common Issues

1. **"Credentials not found" error**:
   - Verify that SecretId and SecretKey are correctly configured
   - Check that the CAM user is active

2. **"Access Denied" error**:
   - Ensure the CAM user has proper COS permissions
   - Verify the bucket policy allows access from your CAM user

3. **"Bucket not found" error**:
   - Check that the bucket name is correct
   - Ensure the bucket exists in the specified region

4. **Region connectivity issues**:
   - Verify the region name is correct (e.g., `ap-beijing`)
   - Ensure the bucket exists in the specified region

## Tencent Cloud Regions

Common Tencent Cloud regions include:
- `ap-beijing` (Beijing)
- `ap-shanghai` (Shanghai)
- `ap-guangzhou` (Guangzhou)
- `ap-chengdu` (Chengdu)
- `ap-singapore` (Singapore)
- `ap-mumbai` (Mumbai)
- `ap-tokyo` (Tokyo)

For a complete list, refer to [Tencent Cloud COS Regions and Endpoints](https://cloud.tencent.com/document/product/436/6224).

## Privacy

Please refer to the [Privacy Policy](PRIVACY.md) for information on how your data is handled when using this plugin.

## Support

For issues or questions:
- Contact: [hello@dify.ai](mailto:hello@dify.ai)
- Repository: Check the project repository for updates and documentation

Last updated: January 2025
# AWS S3 Storage Datasource Plugin

**Author**: langgenius  
**Version**: 0.3.4
**Type**: datasource

## Introduction

This plugin integrates with Amazon Web Services (AWS) S3 Storage, enabling automated access to your S3 buckets and objects. It supports browsing files and folders within S3 buckets and downloading files directly for use in platforms like Dify.

## Features

- **Browse S3 Buckets**: List all available S3 buckets in your AWS account
- **Browse Bucket Contents**: Navigate through folders and files within S3 buckets
- **Download Files**: Retrieve files from S3 buckets for processing
- **Folder Navigation**: Support for hierarchical folder structure browsing
- **Pagination Support**: Efficiently handle large numbers of files with pagination

## Setup

### Prerequisites

Before using this plugin, you need:
1. An AWS account with active S3 service
2. S3 buckets with the files you want to access
3. AWS IAM credentials with appropriate permissions

### Configuration Steps

1. **Create AWS IAM User** (if not already exists):
   - Sign in to the [AWS Management Console](https://console.aws.amazon.com/)
   - Navigate to IAM (Identity and Access Management)
   - Click "Users" → "Add users"
   - Provide a user name (e.g., "dify-s3-plugin")
   - Select "Programmatic access" for Access type

2. **Set Permissions**:
   - Attach policies that grant S3 access:
     - `AmazonS3ReadOnlyAccess` (for read-only access to all buckets)
     - Or create a custom policy with specific bucket permissions:
       ```json
       {
         "Version": "2012-10-17",
         "Statement": [
           {
             "Effect": "Allow",
             "Action": [
               "s3:ListBucket",
               "s3:GetObject",
               "s3:ListAllMyBuckets"
             ],
             "Resource": [
               "arn:aws:s3:::your-bucket-name",
               "arn:aws:s3:::your-bucket-name/*"
             ]
           }
         ]
       }
       ```

3. **Generate Access Keys**:
   - After creating the user, go to the "Security credentials" tab
   - Click "Create access key"
   - Choose "Application running outside AWS"
   - Save the **Access Key ID** and **Secret Access Key** securely

4. **Configure the Plugin in Dify**:
   - **Access Key ID**: Enter the Access Key ID from your AWS IAM user
   - **Secret Access Key**: Enter the Secret Access Key from your AWS IAM user
   - **Region Name**: Enter your AWS region (e.g., `us-east-1`, `eu-west-1`, `ap-southeast-1`)
   - Click "Save" to store the credentials

## Usage

### Browsing Files

The plugin provides an online drive interface for browsing S3 content:

1. **List Buckets**: When no bucket is specified, the plugin lists all available S3 buckets
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
| List Buckets | View all S3 buckets in your AWS account |
| Browse Files | Navigate through files and folders in a bucket |
| Download File | Retrieve file content from S3 |
| Pagination | Handle large file lists with continuation tokens |

## Security Considerations

- **Credentials**: Store your AWS credentials securely and never share them
- **Permissions**: Use the principle of least privilege - grant only necessary S3 permissions
- **Region**: Ensure you're using the correct AWS region for your buckets
- **Encryption**: Consider using S3 server-side encryption for sensitive data

## Troubleshooting

### Common Issues

1. **"Credentials not found" error**:
   - Verify that Access Key ID and Secret Access Key are correctly configured
   - Check that the IAM user is active

2. **"Access Denied" error**:
   - Ensure the IAM user has proper S3 permissions
   - Verify the bucket policy allows access from your IAM user

3. **"Bucket not found" error**:
   - Check that the bucket name is correct
   - Ensure the bucket exists in the specified region

4. **Region connectivity issues**:
   - Verify the region name is correct (e.g., `us-east-1`)
   - Ensure the bucket exists in the specified region

## AWS Regions

Common AWS regions include:
- `us-east-1` (US East - N. Virginia)
- `us-west-2` (US West - Oregon)
- `eu-west-1` (EU - Ireland)
- `ap-southeast-1` (Asia Pacific - Singapore)
- `ap-northeast-1` (Asia Pacific - Tokyo)

For a complete list, refer to [AWS Regions and Endpoints](https://docs.aws.amazon.com/general/latest/gr/rande.html).

## Privacy

Please refer to the [Privacy Policy](PRIVACY.md) for information on how your data is handled when using this plugin.

## Support

For issues or questions:
- Contact: [hello@dify.ai](mailto:hello@dify.ai)
- Repository: Check the project repository for updates and documentation

Last updated: September 2025

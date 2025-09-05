# Azure Blob Storage Datasource Plugin

Access Azure Blob Storage containers and blobs as a datasource for Dify with multiple authentication methods.

## Features

- **Multiple Authentication Methods**: Account key, SAS token, connection string, Azure AD OAuth
- **Container Browsing**: List all accessible storage containers
- **Blob Management**: Browse and download blob files from containers
- **Directory Simulation**: Virtual directory structure based on prefixes
- **Large File Support**: Automatic chunked download for large blob files
- **Multi-Cloud Support**: Global cloud, China cloud, Government cloud, Germany cloud
- **Complete OAuth Support**: Automatic access token refresh without re-authorization
- **Rich Metadata**: Complete blob properties and metadata

## Supported Authentication Methods

### 1. Account Key (Recommended for Development)
- Use storage account name and access key
- Provides full storage account access permissions

### 2. SAS Token (Recommended for Production)
- Use Shared Access Signature token
- Support fine-grained permission control and time limits
- Minimum permissions: read and list permissions

### 3. Connection String
- Use complete connection string
- Contains all required connection information

### 4. Azure AD OAuth (Recommended for Enterprise)
- Use Azure Active Directory authentication
- Support automatic access token refresh
- Multi-cloud environment support (Global, China, Government clouds)
- Principle of least privilege: only requires Storage user impersonation permissions

## Supported Content Types

- All types of blob files
- Automatic MIME type detection
- Support for text, images, documents, archives, etc.
- Large file chunked download (>50MB)

## Azure Cloud Support

- **Global Azure**: core.windows.net (default)
- **Azure China**: core.chinacloudapi.cn
- **Azure Government**: core.usgovcloudapi.net

## Version: 0.2.0

### Features in v0.2.0
- ✅ Account key authentication
- ✅ SAS token authentication  
- ✅ Connection string authentication
- ✅ Container and blob browsing
- ✅ Large file chunked download
- ✅ Multi-cloud environment support
- ✅ Archive tier detection and alerts
- ✅ Complete Azure AD OAuth support
- ✅ Automatic access token refresh

### Security Features
- Secure storage of sensitive credentials
- Permission validation and error handling
- Principle of least privilege
- Secure authentication flows

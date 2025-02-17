## Privacy Policy for OKX Plugin

### Data Collection and Usage

1. **API Credentials**

   - The plugin requires OKX API credentials (API Key, Secret Key, and Passphrase)
   - These credentials are securely stored and managed by Dify's credential management system
   - Credentials are only used to authenticate API requests to OKX

2. **Trading Data**

   - The plugin accesses trading-related data through OKX's API, including:
     - Market prices and trading pairs
     - Account balances
     - Order information
   - This data is only used to execute requested operations
   - No trading data is stored by the plugin

3. **User Data Protection**
   - All API requests are made directly to OKX servers using CCXT library
   - No user data is stored locally or transmitted to third parties
   - All communications are encrypted using HTTPS

### Data Security

1. **Credential Security**

   - API credentials are never exposed in plaintext
   - Credentials are only used for API authentication
   - Users can revoke API access at any time through OKX

2. **Request Security**
   - All API requests are made over secure HTTPS connections
   - API requests are signed using industry-standard cryptographic methods
   - Request parameters are validated before submission

### User Rights

1. **Data Control**

   - Users have full control over their API credentials
   - Users can revoke access at any time
   - No data is retained after plugin uninstallation

2. **Transparency**
   - All plugin operations are documented
   - Source code is available for review
   - No hidden data collection or usage

### Compliance

1. **API Usage**

   - The plugin complies with OKX's API terms of service
   - Rate limits and usage restrictions are respected
   - All trading operations require explicit user authorization

2. **Updates**
   - This privacy policy may be updated to reflect changes in functionality
   - Users will be notified of significant privacy policy changes
   - Latest version always available in the repository

### Contact

For any privacy-related concerns or questions, please:

1. Open an issue in the plugin repository
2. Contact the plugin author
3. Contact Dify support for platform-related privacy concerns

### Note

This plugin is provided for cryptocurrency trading purposes. Users are responsible for:

- Securing their API credentials
- Understanding the risks of cryptocurrency trading
- Complying with local regulations regarding cryptocurrency trading

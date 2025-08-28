# Privacy Policy - Spotify Plugin

**Last Updated**: August 2025
**Plugin Version**: 0.1.0
**Author**: langgenius

## Overview

This privacy policy describes how the Spotify Plugin for Dify handles user data when you use our plugin to interact with Spotify services. We are committed to protecting your privacy and being transparent about our data practices.

**Important Note**: This plugin acts as a secure intermediary between Dify and Spotify. **Dify does not collect, store, or retain your personal Spotify data**. All data is passed directly to and from Spotify's services to provide functionality within the Dify platform.

## Data Collection and Use

### Does this plugin collect and use personal data?

**Dify does not collect or store this data**. The plugin acts as a secure bridge that allows Dify to communicate with Spotify on your behalf. All data remains between you and Spotify, with Dify serving only as a conduit to enable the integration.

### Types of Data Accessed (Not Collected by Dify)

**Important**: The following data types are accessed from Spotify and passed through Dify to provide plugin functionality. **Dify does not collect, store, or retain any of this information**.

#### Type A: Direct Identifiers
- **Spotify Username**: Your Spotify account username/display name (passed through to display)
- **Email Address**: Associated with your Spotify account (if publicly available and accessed by Spotify API)

#### Type B: Indirect Identifiers
- **Device Information**: Information about devices where Spotify is active (device names, types, and IDs) - used for playback control
- **IP Address**: Your IP address as part of Spotify API requests (not stored by Dify)
- **Location Data**: Market/country information for content availability (used for regional content filtering)
- **Online Identifiers**: Spotify user ID, playlist IDs, track IDs, album IDs, artist IDs (used for content identification)

#### Type C: Data Combined with Other Information
- **Music Preferences**: Listening history, saved tracks, followed artists, playlists (accessed to provide recommendations)
- **Playback Data**: Currently playing tracks, playback state, recently played items (used for playback control)
- **Library Information**: Saved albums, playlists (both public and private), followed artists (accessed for library management)
- **Top Content**: Your most played tracks and artists (accessed for personalization)
- **Usage Patterns**: Music streaming behavior and preferences (accessed to improve user experience)

### Specific Spotify Data Access

Through the OAuth authorization, this plugin requests access to the following Spotify data via these scopes:

- **`user-read-playback-state`**: Current playback information and active devices
- **`user-modify-playback-state`**: Control playback (play, pause, skip, volume, etc.)
- **`user-read-currently-playing`**: Currently playing track information
- **`streaming`**: Control Spotify Connect devices and playback
- **`user-library-read`**: Access to your saved tracks and albums
- **`user-library-modify`**: Ability to save/remove tracks and albums
- **`playlist-read-private`**: Access to your private playlists
- **`playlist-modify-public`**: Modify your public playlists
- **`playlist-modify-private`**: Modify your private playlists
- **`user-follow-read`**: Artists and users you follow
- **`user-follow-modify`**: Follow/unfollow artists and users
- **`user-top-read`**: Your top tracks and artists
- **`user-read-recently-played`**: Recently played tracks

## How Data Flows Through This Plugin

**Dify does not use or store your data**. Instead, data flows as follows:

1. **Data Access**: When you authorize the plugin, it gains permission to access your Spotify data
2. **Pass-Through Processing**: The plugin requests data from Spotify and immediately passes it through Dify to provide functionality
3. **Real-Time Operations**: All operations are performed in real-time without storing data on Dify servers
4. **Direct Communication**: Your data flows directly between Spotify and the plugin functionality within Dify

The plugin facilitates these operations:

1. **Search and Discovery**: Pass search queries to Spotify and return results through Dify
2. **Playback Control**: Relay playback commands to your Spotify-connected devices
3. **Library Management**: Forward library modification requests to Spotify
4. **Device Management**: Retrieve and display your Spotify-enabled devices
5. **Content Retrieval**: Fetch and display detailed information about tracks, albums, and artists
6. **User Experience**: Enable personalized features by accessing your Spotify listening data

## Data Storage and Security

**Dify's Data Handling**:
- **No Data Collection**: Dify does not collect your personal Spotify data
- **No Persistent Storage**: Dify does not store your Spotify data on its servers
- **Pass-Through Only**: Data is only temporarily processed in memory to facilitate communication with Spotify
- **Real-Time Processing**: All operations are performed in real-time without data retention

**Security Measures**:
- **Secure Transmission**: All data transmission between Dify and Spotify uses HTTPS encryption
- **OAuth Security**: Access tokens are securely managed within the session and automatically refreshed
- **No Local Storage**: Your personal data is not stored locally by the Dify plugin
- **Encrypted Communication**: All API communications are encrypted and secure

## Third-Party Data Sharing

### Spotify
This plugin integrates directly with Spotify's services. All data access is governed by:
- **Spotify's Privacy Policy**: https://www.spotify.com/legal/privacy-policy/
- **Spotify's Terms of Service**: https://www.spotify.com/legal/end-user-agreement/

When you use this plugin, your data is shared with Spotify according to their privacy policy and terms of service.

### Dify Platform
This plugin operates within the Dify platform environment. Please refer to:
- **Dify's Privacy Policy**: https://dify.ai/privacy

### No Additional Third Parties
**Dify does not share your data with any third-party services**. The plugin only facilitates direct communication between you and Spotify. No data is shared with additional third parties beyond this direct integration.

## Data Retention

**Dify's Data Retention Policy**:
- **No Data Retention**: Dify does not retain any of your personal Spotify data
- **Session-Only Processing**: Data is processed only during active plugin sessions and immediately discarded
- **OAuth Tokens**: Only access and refresh tokens are temporarily stored to maintain authorization (these can be revoked anytime)
- **Zero Long-term Storage**: Dify maintains no long-term storage of your personal Spotify information

**Your Data Remains with Spotify**: All your personal data, music preferences, and account information remain exclusively with Spotify under their data retention policies.

## Your Rights and Choices

### Access Control
- You maintain full control over your Spotify account and data
- You can revoke plugin access at any time through your Spotify account settings

### Data Deletion
- Disconnect the plugin through Dify settings to stop data access
- Revoke app permissions in your Spotify account settings at: https://www.spotify.com/account/apps/

### Spotify Account Management
- Manage your Spotify privacy settings at: https://www.spotify.com/account/privacy/

## Children's Privacy

This plugin is not intended for use by children under 13 years of age. We do not knowingly collect personal information from children under 13. If you believe we have collected information from a child under 13, please contact us immediately.

## Changes to This Privacy Policy

We may update this privacy policy from time to time. Any changes will be reflected in the "Last Updated" date at the top of this policy. Continued use of the plugin after changes constitutes acceptance of the updated policy.

## Contact Information

For questions about this privacy policy or our data practices, please contact:

- **Plugin Developer**: langgenius
- **GitHub Repository**: [Dify Official Plugins](https://github.com/langgenius/dify-official-plugins)
- **Dify Support**: hello@dify.ai

## Compliance

This privacy policy is designed to comply with:
- General Data Protection Regulation (GDPR)
- California Consumer Privacy Act (CCPA)
- Other applicable privacy laws and regulations

By using this plugin, you acknowledge that you have read and understood this privacy policy and consent to the data practices described herein.

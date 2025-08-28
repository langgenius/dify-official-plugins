# Google Contacts Plugin

**Author**: langgenius
**Version**: 0.1.0
**Type**: tool

## Introduction

This plugin integrates with Google Contacts through the People API, supporting comprehensive contact management operations. It enables automated contact management in platforms like Dify, allowing you to create, read, update, delete, search, and list contacts in your Google account.

## Setup

1. Register your application in the [Google Cloud Console](https://console.developers.google.com/).

2. Create a new application as follows:
    - **Project Name**: Dify Google Contacts Plugin
    - **Enable APIs**: Go to "APIs & Services" > "Library", search for and enable "People API"

    <p align="center">
        <img src="_assets/enable_api.png" alt="Enable People API" width="600" />
    </p>

    - **Create Credentials**: Select "OAuth 2.0 Client ID"

    <p align="center">
        <img src="_assets/create_oauth_client.png" alt="Create OAuth Client" width="600" />
    </p>

    - **Application Type**: Choose "Web application"
    - **Redirect URI**: Set the redirect URI to:
        - For SaaS (cloud.dify.ai) users: please use `https://cloud.dify.ai/console/api/oauth/plugin/langgenius/google_contacts/google_contacts/tool/callback`
        - For self-hosted users: please use `http://<YOUR_LOCALHOST_CONSOLE_API_URL>/console/api/oauth/plugin/langgenius/google_contacts/google_contacts/tool/callback`
        ***Due to the restrictions of the Google OAuth2 flow, redirect URIs must start with `https://` or `http://localhost`.***



3. Copy your **Application (client) ID**

    <p align="center">
        <img src="_assets/get_client_id.png" alt="Get Client ID" width="600" />
    </p>

4. Create a new client secret:
    - **Description**: Dify Google Contacts Plugin Secret
    - **Expires**: Whatever duration you prefer (e.g., 1 year, 2 years, etc.)
    - Copy the generated **Value** of the client secret.

5. Add a test user to the People API:
    - Go to "APIs & Services" > "Credentials" > "OAuth consent screen" > "Test Users"
    - Add a test user with the email address you want to use for testing.

    <p align="center">
        <img src="_assets/add_test_user.png" alt="Add Test User" width="600" />
    </p>

6. Configure the plugin in Dify:
    - Fill in the **Client ID** and **Client Secret** fields with the values you copied from the Google Cloud Console.
    - Make sure you have the same redirect URI as specified in the Google Cloud Console. If not, you will need to update it in the Google Cloud Console.
    - Click `Save and authorize` to initiate the OAuth flow.

7. Enjoy using the Google Contacts plugin in Dify!

## Tool Descriptions

### list_contacts
Retrieve a list of contacts from Google Contacts with pagination support.

**Parameters:**
- page_size (number, optional): Number of contacts to retrieve per page (1-2000, default: 25)
- page_token (string, optional): Token for retrieving the next page of results (leave empty for first page)
- person_fields (string, optional): Comma-separated list of person fields to include (default: "names,phoneNumbers,emailAddresses")

**Returns:** Contact information including names, phone numbers, email addresses, organization details, and pagination tokens.

### search_contacts
Search for contacts in Google Contacts using a query string.

**Parameters:**
- query (string, required): Search term to find contacts (name, email, phone, etc.)
- page_size (number, optional): Number of search results to return (1-50, default: 25)

**Returns:** Array of matching contacts with their details including names, phone numbers, email addresses, organizations, and addresses.

### create_contact
Create a new contact in Google Contacts.

**Parameters:**
- given_name (string, optional): First name of the contact
- family_name (string, optional): Last name of the contact
- middle_name (string, optional): Middle name of the contact
- phone_number (string, optional): Phone number of the contact
- email_address (string, optional): Email address of the contact
- organization (string, optional): Company or organization name
- job_title (string, optional): Job title or position
- notes (string, optional): Additional notes or comments about the contact

**Returns:** Success status and created contact information with Google's unique resource identifier.

### get_contact
Get detailed information about a specific contact using its resource name.

**Parameters:**
- resource_name (string, required): Google's unique resource identifier for the contact (format: people/contactId)
- person_fields (string, optional): Comma-separated list of person fields to include (default includes comprehensive fields)

**Returns:** Comprehensive contact details including names, phone numbers, email addresses, organizations, addresses, biographies, birthdays, URLs, and relations.

### update_contact
Update an existing contact in Google Contacts.

**Parameters:**
- resource_name (string, required): Google's unique resource identifier for the contact to update
- given_name (string, optional): Updated first name
- family_name (string, optional): Updated last name
- middle_name (string, optional): Updated middle name
- phone_number (string, optional): Updated phone number
- email_address (string, optional): Updated email address
- organization (string, optional): Updated company or organization name
- job_title (string, optional): Updated job title or position
- notes (string, optional): Updated notes or comments

**Returns:** Success status, list of updated fields, and updated contact information.

### delete_contact
Delete a contact from Google Contacts (CAUTION: This action cannot be undone).

**Parameters:**
- resource_name (string, required): Google's unique resource identifier for the contact to delete
- confirm_delete (boolean, required): Must be set to true to confirm the deletion

**Returns:** Success status and confirmation of deleted contact information.

## Privacy

When using this plugin, your Google Contacts data will be accessed through a secure OAuth connection. The plugin only accesses and operates on your contact data within the scope you authorize. Please refer to Google's privacy policy for more information about data handling.

## Usage Examples

1. **View Contact List**: Use the `list_contacts` tool to view all your contacts with pagination support
2. **Search for Someone**: Use the `search_contacts` tool to find contacts by name, email, or phone number
3. **Add New Contact**: Use the `create_contact` tool to add a new contact with name, phone, email, and organization details
4. **Get Contact Details**: Use the `get_contact` tool to retrieve comprehensive information about a specific contact
5. **Update Contact Info**: Use the `update_contact` tool to modify existing contact information
6. **Remove Contact**: Use the `delete_contact` tool to permanently delete a contact (use with caution)

Last updated: December 2024
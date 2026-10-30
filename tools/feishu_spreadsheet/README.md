# Feishu Spreadsheet

Feishu Spreadsheet, requires the following permissions: sheets:spreadsheet.

## Features
- Create Spreadsheet.
- Add Rows.
- Read Rows.
- Read Table.
- Get Spreadsheet.
- Read Cols.
- Add Cols.
- List Spreadsheet Sheets.

## Setup
1. Install this plugin from the Dify Marketplace.
2. Prepare the required credentials: APP ID, APP Secret.
3. Add the credentials in the plugin settings.
4. Save the configuration.

## Usage
Add the Feishu Spreadsheet tools to an agent or workflow, fill in the required inputs, and run the node to call the upstream service.

## Privacy
This plugin sends the inputs required by the selected operation to the upstream service. Review the upstream service's privacy policy before use.


## Custom API Base URL

Set **API Base URL** in the plugin credentials to use a self-hosted compatible proxy service (for example, `https://proxy.example.com/lark-plugin`). The default remains `https://lark-plugin-api.solutionsuite.cn/lark-plugin`. Existing credentials without this field and blank values also use the default service.

The custom service must implement the existing proxy API contract, including token acquisition and business endpoints. The Feishu Open Platform API URL is not a direct replacement. Credential validation and all tool requests use this address.

# HAP Application Tool

AI-friendly hyper application platform for no-code enterprise applications and hyper-automation workflows.

## Features
- Get Application Info: Get application information, including groups, worksheets, and custom pages.
- Get Worksheet Structure: Get worksheet structure using worksheet_id.
- List Records: List worksheet records with pagination, filtering and sorting.
- Get Record Pivot Data: Get pivot table data for worksheet records.
- Create Record: Create a new record in a worksheet by field ID/value mapping. Default triggers workflow.
- Update Record: Update a record by row id in a worksheet.
- Delete Record: Delete a record by row_id in a worksheet.
- Get Record Details: Get record details by worksheet ID and row ID.

## Setup
1. Install this plugin from the Dify Marketplace.
2. Prepare the required credentials: Application Appkey, Application Sign, API Base URL (Optional, required for private deployment).
3. Add the credentials in the plugin settings.
4. Save the configuration.

## Usage
Add the HAP Application Tool tools to an agent or workflow, fill in the required inputs, and run the node to call the upstream service.

## Privacy
This plugin sends the inputs required by the selected operation to the upstream service. Review the upstream service's privacy policy before use.

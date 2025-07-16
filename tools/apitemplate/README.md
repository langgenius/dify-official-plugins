# APITemplate.io Plugin for Dify

This plugin integrates APITemplate.io's document and image generation capabilities with Dify, allowing you to create professional PDFs, images, and documents from templates or HTML content directly from your Dify applications.

## Features

- **Create PDF from Template**: Generate PDFs using pre-designed templates with custom data
- **Create Image from Template**: Generate JPEG and PNG images from templates with dynamic content
- **Create PDF from HTML**: Convert HTML content with CSS styling to PDF documents
- **Create PDF from URL**: Capture web pages and convert them to PDF format
- **Delete Object**: Remove generated files from APITemplate.io CDN
- **Get Account Information**: Retrieve account details, quotas, and usage statistics
- **List Objects**: Browse all generated files with filtering and pagination

## Installation

1. Install the plugin through Dify's Plugin Marketplace.
2. Configure the plugin with your APITemplate.io API key.

## Authentication

You'll need an **APITemplate.io API key** to use this plugin:

1. Log in to [APITemplate.io](https://app.apitemplate.io)
2. Go to your dashboard and navigate to **Manage API**
3. Generate a new API key or copy an existing one
4. Copy the API key immediately (keep it secure)
5. Paste the key into the **API Key** field in the plugin configuration

**Important**: Your API key grants access to your APITemplate.io account and usage quotas. Keep it secure and never share it publicly.

## Usage

The plugin provides the following tools that can be used in your Dify applications:

### Create PDF from Template

Generates a PDF document using a pre-designed template from your APITemplate.io account.

Required parameters:
- `template_id`: The unique identifier of the PDF template (found in your APITemplate.io dashboard)
- `json_data`: JSON object containing the data to populate the template fields

Optional parameters:
- `filename`: Custom filename for the generated PDF (must end with .pdf)

Example:
```
Create a PDF using template 79667b2b1876e347 with data {"name": "John Doe", "invoice_number": "INV-001", "amount": "$1,000"}
```

### Create Image from Template

Generates JPEG and PNG images from a template with custom data.

Required parameters:
- `template_id`: The unique identifier of the image template
- `overrides_data`: JSON object with overrides array containing modifications for template elements

Optional parameters:
- `output_image_type`: Image format ("all", "jpegOnly", or "pngOnly")

Example:
```
Create an image using template abc123 with overrides {"overrides": [{"name": "text_1", "text": "Hello World"}]}
```

### Create PDF from HTML

Converts HTML content with optional CSS styling to a PDF document.

Required parameters:
- `html_body`: HTML content for the PDF body (supports Jinja2 templating)

Optional parameters:
- `css_styles`: CSS styles to apply to the PDF
- `template_data`: JSON data for Jinja2 template variables
- `filename`: Custom filename for the generated PDF

Example:
```
Create a PDF from HTML content "<h1>Invoice {{invoice_number}}</h1>" with data {"invoice_number": "INV-001"}
```

### Create PDF from URL

Captures a web page and converts it to PDF format.

Required parameters:
- `url`: Complete URL of the web page to convert (must include http:// or https://)

Optional parameters:
- `paper_size`: Paper size (A4, Letter, Legal, etc.)
- `orientation`: Page orientation ("1" for portrait, "2" for landscape)
- `filename`: Custom filename for the generated PDF

Example:
```
Create a PDF from the URL https://example.com/report with A4 paper size
```

### Delete Object

Removes a generated PDF or image from APITemplate.io CDN.

Required parameters:
- `transaction_ref`: Transaction reference ID returned when the file was created

Example:
```
Delete the object with transaction reference 1618d386-2343-3d234-b9c7-99c82bb9f104
```

### Get Account Information

Retrieves comprehensive account information including subscription status, quotas, and usage.

No parameters required.

Example:
```
Get my APITemplate.io account information
```

### List Objects

Lists all generated PDFs and images with filtering and pagination options.

Optional parameters:
- `limit`: Number of records to retrieve (default: 300, max: 300)
- `offset`: Number of records to skip for pagination (default: 0)
- `transaction_type`: Filter by file type ("PDF", "JPEG", or "MERGE")

Example:
```
List the last 50 PDF files from my account
```

## Template Management

To use template-based generation:

1. Create templates in your APITemplate.io dashboard
2. Note the template ID from the template details page
3. Design your template with placeholder fields
4. Use the template ID in the Dify plugin calls

## Troubleshooting

If you encounter issues with the plugin:

- Verify your API key is correct and active
- Check that template IDs exist and are accessible with your account
- Ensure your APITemplate.io account has sufficient quota
- For HTML to PDF conversion, validate your HTML and CSS syntax
- For URL to PDF conversion, ensure the target URL is publicly accessible
- Check network connectivity if requests are timing out

## Supported Formats

**PDF Generation:**
- Template-based PDFs with dynamic data
- HTML to PDF with CSS styling
- URL to PDF conversion
- Various paper sizes and orientations

**Image Generation:**
- JPEG format images
- PNG format images  
- Template-based with dynamic content
- Custom sizing and formatting

## Usage Limits

Usage limits depend on your APITemplate.io subscription plan:
- API request limits per month
- File storage limits
- Template creation limits

Check your account information using the "Get Account Information" tool to monitor usage.


# Attio Plugin for Dify

**Author:** langgenius  
**Version:** 0.0.1  
**Type:** Tool

---

## Overview

The Attio Plugin connects [Dify](https://dify.ai/) with [Attio](https://www.attio.com/) to manage CRM data and automate operations such as listing, creating, updating, and deleting records, objects, lists, and attributes in your Attio workspace.

*Attention* If you need to use filtering and sorting in List Record/List Entries, please view rules [here](https://attio.mintlify.app/rest-api/how-to/filtering-and-sorting), you can create agents to help you with that.

---

## Features

- List, create, update, and delete records in Attio objects and lists
- Retrieve and manage Attio objects, lists, and their attributes
- Filter, sort, and paginate records and entries
- Secure API token authentication

---


## Usage

Each tool is defined by a YAML file in the `tools/` directory and implemented in the corresponding Python file.  
You can invoke these tools from Dify workflows or via API calls.

### Example: List Records in an Attio Object

```yaml
parameters:
  object_slug: "your-object-slug"
  filters: '{"status": "active"}'   # optional
  sorts: '[{"created_at": "desc"}]' # optional
  limit: 100                        # optional
  offset: 0                         # optional
```

### Available Tools

- **add_records**: Add one or more records to an Attio object.
- **list_records**: List all records in an Attio object, with optional filters and sorting.
- **delete_records**: Delete a record from an Attio object.
- **list_objects**: List all objects in Attio.
- **create_objects**: Create a new object in Attio.
- **list_lists**: List all lists in Attio.
- **list_entries**: List all entries in an Attio list, with optional filters and sorting.
- **add_entries**: Add entries to an Attio list.
- **delete_entries**: Delete an entry from an Attio list.
- **list_attributes**: List all attributes for a given Attio object or list.

Each tool's YAML file documents the required and optional parameters.

---

## Development

- All tool logic is implemented in the `tools/` directory.
- To add or modify tools, edit the corresponding `.py` and `.yaml` files.
- Follow the parameter and description conventions for consistency.
- See [GUIDE.md](./GUIDE.md) for more details on plugin development.

Several Function are under developing:

- Add Entries
- Delete Entries
- Create Object

Will be finished soon, you might meet some bugs when use these functions.


---

## Security & Privacy

- Your **Attio API Token** is used only for authenticating API requests to Attio.
- No personal data is stored or shared by this plugin.
- See [PRIVACY.md](./PRIVACY.md) for full details.

---

## Testing & Debugging

- Copy `.env.example` to `.env` and fill in your configuration for local debugging.
- Run the plugin with:
  ```bash
  python -m main
  ```
- You should see your plugin in the Dify instance plugin list (marked as "debugging" if running locally).

---

## License

This plugin is provided as-is for integration with Dify and Attio.
See LICENSE file if present.

---

_Last updated: July 9, 2025_
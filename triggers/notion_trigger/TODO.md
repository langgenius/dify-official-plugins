# Notion Trigger TODO

- [x] Replace Linear-specific README content with Notion onboarding instructions (webhook setup, verification token, required capabilities).
- [x] Implement Notion-specific provider metadata in `provider/notion_simple.yaml` (event list, localized descriptions).
- [x] Flesh out `NotionTrigger` signature validation and mapping tests.
- [x] Implement subscription constructor unit tests to ensure verification token stored.
- [x] Define event YAML/Python pairs for all supported Notion event types (pages, databases, data sources, comments).
- [x] Create sample payload fixtures based on `notion.md` for unit tests.
- [x] Update `tests` suite to cover Notion events and provider dispatch behaviour.
- [ ] Update packaging metadata (`manifest.yaml`) and run plugin packaging when ready for release.

## Notion Trigger Content Enrichment - Phase Tracking

- [x] Phase 1 – Infrastructure
  - [x] Add `notion_integration_token` secret parameter to `provider/notion_simple.yaml`.
  - [x] Persist integration token inside subscription properties in `provider/notion_simple.py`.
  - [x] Introduce `notion_trigger/notion_client.py` module skeleton.
- [x] Phase 2 – Notion API Client
  - [x] Implement `NotionClient.fetch_page`.
  - [x] Implement `NotionClient.fetch_database`.
  - [x] Implement `NotionClient.fetch_data_source`.
  - [x] Implement `NotionClient.fetch_block` and optional `fetch_block_children`.
  - [x] Implement `NotionClient.fetch_comment` with graceful fallbacks.
  - [x] Add shared error handling and lightweight retry helpers.
- [x] Phase 3 – Event Enhancements
  - [x] Extend `events/base.py` to hydrate entity content via `NotionClient`.
  - [x] Update page event output schemas with `entity_content`.
  - [x] Update database event output schemas with `entity_content`.
  - [x] Update data_source event output schemas with `entity_content`.
  - [x] Update comment event output schemas with `entity_content`.
- [x] Phase 4 – Testing
  - [x] Add unit tests covering client usage and hydrated event variables.
  - [x] Update existing tests to account for new parameters and outputs.

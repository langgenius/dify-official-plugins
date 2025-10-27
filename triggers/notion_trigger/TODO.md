# Notion Trigger TODO

- [x] Replace Linear-specific README content with Notion onboarding instructions (webhook setup, verification token, required capabilities).
- [x] Implement Notion-specific provider metadata in `provider/notion_simple.yaml` (event list, localized descriptions).
- [x] Flesh out `NotionTrigger` signature validation and mapping tests.
- [x] Implement subscription constructor unit tests to ensure verification token stored.
- [x] Define event YAML/Python pairs for all supported Notion event types (pages, databases, data sources, comments).
- [x] Create sample payload fixtures based on `notion.md` for unit tests.
- [x] Update `tests` suite to cover Notion events and provider dispatch behaviour.
- [ ] Update packaging metadata (`manifest.yaml`) and run plugin packaging when ready for release.

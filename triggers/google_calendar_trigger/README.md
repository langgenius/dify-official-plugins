# Google Calendar Trigger

## Why use it?

- Let your Dify workflow react the moment a Google Calendar event is created, updated, or cancelled.
- Every change is split into familiar events:
  - `google_calendar_event_created`: first time we see the event (even if Google instantly adds a Meet link or reminder).
  - `google_calendar_event_updated`: an existing event gets edited (time, location, attendees, notes, etc.).
  - `google_calendar_event_deleted`: the event was cancelled/removed (optional).
- "Fetch full details" lets you pull attendees, conference links, room info, etc. Turn it off if you just need a light signal.

## What you need beforehand

1. A Google account that can access the calendar (personal or Workspace).
2. Calendar API enabled in Google Cloud Console, plus an **OAuth 2.0 Web application** client (Client ID & Secret).
3. Your Dify instance must be reachable from the internet so Google can deliver the webhook.

## Setup

1. **Import the plugin**  
   Dify → Plugin Center → “Import plugin”, choose `google_calendar_trigger`. For local dev, drop the folder into `plugins/` and run normally.

2. **Enter OAuth credentials**  
   Fill in Client ID / Secret → Save → click “Authorize”, sign in with Google, and grant `calendar.readonly`.  
   ![OAuth client](./_assets/GC_OAUTH_CLIENT.png)

3. **Create a subscription**  
   - `Calendar`: which calendar to watch (default `primary`).  
   - `Include Cancelled Events`: whether cancelled meetings should trigger events (default on).  
   - `Fetch Full Event Details`: fetch attendees/conference links for each change (default on; disable for lower latency/quota).  
   After saving, the plugin registers a webhook and starts listening automatically.

## How it works

1. Google’s webhook only says “this calendar changed”. We keep a `syncToken` and call `events.list(syncToken=...)` to fetch the exact changes—no duplicates, no gaps.
2. To tell “created” from “updated”, we combine `sequence` with the gap between `created` and `updated`. If `sequence ≤ 1` *and* the timestamps differ by ≤5 seconds, it counts as the first appearance.
3. Want the full payload in your workflow? Keep “Fetch Full Event Details” on. Prefer lightweight data? Turn it off and we just return the base fields.

## What can you build?

- **Customer success / sales**: auto-generate prep notes or create CRM tasks when a new meeting appears.
- **Project coordination**: notify teammates or update task boards the moment a meeting is rescheduled.
- **Admin / resource ops**: release rooms, cancel catering/travel when a meeting is deleted.
- **Simple reminders**: disable enrichment and treat “calendar was touched” as a low-cost signal.

## FAQ

- **Webhook isn’t firing?**  
  Ensure Dify is reachable from the internet, OAuth hasn’t expired, and the target calendar actually changed. Calendar API metrics in Google Cloud Console can help debug.  
- **Worried about quota or latency?**  
  Turn off “Fetch Full Event Details” to skip the extra `events.get` calls.  
- **Got HTTP 410 / sync token expired?**  
  The trigger automatically refreshes the sync token. If nothing arrives for a long time, re-authorize once.

## Need help?

- Google Calendar push guide: https://developers.google.com/calendar/api/guides/push  
- Sync mechanism: https://developers.google.com/calendar/api/guides/sync  
- Dify docs: https://docs.dify.ai

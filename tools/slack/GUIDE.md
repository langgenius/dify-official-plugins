# Slack Plugin — Quick Guide

## Setup
1. Create a Slack app (https://api.slack.com/apps) and add Bot Token Scopes.
2. Install it and copy the Bot User OAuth Token (`xoxb-…`).
3. In Dify, set the **Slack Bot Token** credential. Add a **Slack User Token**
   (`xoxp-…`) too if you need Search, Stars, or Update Profile.

## Common tasks
- **Post a message** — Send Message: `channel` = `C012AB3CD`, `text` = "Hello".
- **Reply in a thread** — Send Message with `thread_ts` set to the parent ts.
- **Read recent messages** — Get Channel History with `channel`.
- **React** — Add Reaction: `channel`, `timestamp`, `name` = `thumbsup`.
- **Upload a file** — Upload File with a `file` (or `content` + `filename`) and
  optional `channel`.
- **Find a channel/user ID** — List Channels / List Users.

## Tips
- Emoji names go without colons (`thumbsup`, not `:thumbsup:`).
- `timestamp`/`ts` is the message's Slack timestamp (e.g. `1716999999.000200`).
- Operations marked ⚠️ in the README need the User Token.

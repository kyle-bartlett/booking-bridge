# booking-bridge

A native Hermes plugin that finds free time, books, lists, reschedules and cancels real Google Calendar consults (for example a "Strategy consult"). It uses Hermes' own Google sign-in; the plugin never holds a token.

## Tools

| Tool | What it does |
|---|---|
| `list_availability` | Real free slots via Google FreeBusy (window capped at 14 days). Never invents times. |
| `list_upcoming` | Next events (max 25): id, title, start, end, link, status. |
| `book_event` | Re-checks FreeBusy, refuses on conflict, idempotent on retry. Needs `confirm: true`. |
| `reschedule_event` | Moves an event to a free time. Needs `confirm: true`. |
| `cancel_event` | Deletes an event. Needs `confirm: true`. |

Write tools refuse to run in cron or webhook-style unattended sessions.

## Install

1. In Google Cloud, enable the Calendar API and create an OAuth client of type "Desktop app" ([credentials](https://console.cloud.google.com/apis/credentials)).
2. `hermes plugins install kyle-bartlett/booking-bridge`
3. Set `BOOKING_BRIDGE_CLIENT_ID` and `BOOKING_BRIDGE_CLIENT_SECRET` when Hermes asks.
4. `hermes auth add booking-bridge:google`

Settings (`plugins.entries.booking-bridge.settings`): `default_calendar` (primary), `default_timezone` (America/Chicago), `default_duration_minutes` (30).

## Disclosures

- Network: only `https://www.googleapis.com` (Google Calendar API v3), through Hermes' `credentialed_provider_request`. Scopes: `calendar.events`, `calendar.freebusy`.
- Credentials: you supply your own Google OAuth client; Hermes stores and refreshes the token. The plugin reads no files, `.env`, `auth.json` or keychains.
- Calendar changes: book, reschedule and cancel write to your calendar and can send invitation emails to attendees you list. They require `confirm: true`.
- Booked events carry a private extended property `bookingBridgeKey` (a hash) used to avoid duplicate bookings.
- No shell commands, no background processes, no telemetry, no self-update.

## Develop

`python -m unittest discover -s tests` (mocked HTTP, no live Google). `hermes plugins validate . --install-deps` and `hermes plugins doctor . --ci`.

MIT licensed.

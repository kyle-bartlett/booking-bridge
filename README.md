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

Slash command: `/booking status` shows whether Google is signed in and your next events.

### When write tools run
`book_event`, `reschedule_event` and `cancel_event` need `confirm: true`, which the agent sets only after you agree to the exact action in the conversation. They run only when the plugin can tell a person is present, using an **allowlist**:

- **Run:** an interactive CLI, TUI, Desktop or ACP session, and these human chat platforms: Telegram, Discord, Slack, WhatsApp (including WhatsApp Cloud), Signal, Mattermost, Matrix, BlueBubbles. Your reply in the chat is the approval.
- **Refuse, changing nothing:** cron runs, single-query / one-shot runs (`hermes chat -q`, `hermes -z`), kanban workers, the `webhook`, `msgraph_webhook` and `api_server` platforms, email, SMS, and **any platform or session source not named above**, including new or unknown ones.

Read-only tools (`list_availability`, `list_upcoming`) work everywhere.

This is a conversational confirmation, not a Hermes approval card: Hermes does not route plugin tool calls through its dangerous-command approval prompt, and `ctx.ask_choice` only works inside a user-typed slash command, never in an agent tool call. The plugin never auto-approves, never touches Hermes' approval settings, and never waits on a prompt, so it cannot hang an unattended run.

**Known limit:** a one-shot (`-q` / `-z`) turn submitted through the gateway daemon carries its "finite" flag in a private Hermes context variable that plugins cannot read. The plugin refuses it when Hermes also marks the session as one-shot (`HERMES_SINGLE_QUERY_SESSION` or a `oneshot` session source), but cannot detect a finite daemon turn that carries neither marker and runs on a local surface. `confirm: true` is still required there.

## Install

1. In Google Cloud, enable the Calendar API and create an OAuth client of type "Desktop app" ([credentials](https://console.cloud.google.com/apis/credentials)).
2. `hermes plugins install kyle-bartlett/booking-bridge`
3. Set `BOOKING_BRIDGE_CLIENT_ID` and `BOOKING_BRIDGE_CLIENT_SECRET` when Hermes asks.
4. `hermes auth add booking-bridge:google` (revoke later with `hermes auth logout booking-bridge:google`)

Settings (`plugins.entries.booking-bridge.settings`): `default_calendar` (primary), `default_timezone` (America/Chicago), `default_duration_minutes` (30).

## Revoke access

- In Hermes: `hermes auth logout booking-bridge:google` removes the stored Google sign-in. Run `hermes auth add booking-bridge:google` to sign in again.
- At Google: remove the grant at <https://myaccount.google.com/permissions> (pick your OAuth client, then "Delete all connections"). This also invalidates the token if Hermes cannot reach it.

## Disclosures

- Network: only `https://www.googleapis.com` (Google Calendar API v3), through Hermes' `credentialed_provider_request`. Scopes: `calendar.events`, `calendar.freebusy`.
- Credentials: you supply your own Google OAuth client; Hermes stores and refreshes the token. The plugin reads no files, `.env`, `auth.json` or keychains.
- Calendar changes (only when you confirm in an attended session, see above): book, reschedule and cancel write to your calendar and can send invitation emails to attendees you list. They require `confirm: true`.
- Booked events carry a private extended property `bookingBridgeKey` (a hash) used to avoid duplicate bookings.
- Revoking: `hermes auth logout booking-bridge:google`, or remove the grant at <https://myaccount.google.com/permissions> (see "Revoke access").
- No shell commands, no background processes, no telemetry, no self-update.

## Develop

`python -m unittest discover -s tests` (mocked HTTP, no live Google). `hermes plugins validate . --install-deps` and `hermes plugins doctor . --ci`.

MIT licensed.

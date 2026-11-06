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
Two layers guard `book_event`, `reschedule_event` and `cancel_event`.

**Layer 1, Hermes' approval gate.** The plugin registers a `pre_tool_call` hook that returns `{"action": "approve"}` for those three tools. Hermes then shows its approval prompt (Once, Session or Always) with a plain-English summary of the exact action, and the call runs only if you approve. "Always" is scoped to that exact set of arguments, not to every booking. By default Hermes denies the call where nobody can answer: cron runs, single-query / one-shot runs (`hermes chat -q`, `hermes -z`, including ones submitted through the gateway daemon) and the `webhook`, `msgraph_webhook` and `api_server` platforms; in the classic CLI a delegated sub-agent is denied unless `delegation.subagent_auto_approve` is true, and in gateway sessions it asks you. The plugin uses only the public hook contract and reads no private Hermes state for this.

Hermes settings that are yours to choose switch that gate off, and the plugin respects them: `approvals.mode: off`, YOLO mode (`--yolo`, `/yolo`), `approvals.cron_mode`, `approvals.single_query_mode` or `approvals.unattended_mode` set to `approve`, and `delegation.subagent_auto_approve: true`. With any of these set, only layer 2 remains.

**Layer 2, the plugin's own checks.** Each write needs `confirm: true` (the agent sets it only after you agree to the exact action) and passes an **allowlist** of the session's platform and source values, read with Hermes' documented `get_session_env`:

- **Allowed values:** empty (the interactive CLI and ACP bind no platform or source), `local`, `cli`, `tui`, `desktop`, `acp`, and the human chat platforms `telegram`, `discord`, `slack`, `whatsapp`, `whatsapp_cloud`, `signal`, `mattermost`, `matrix`, `bluebubbles`.
- **Refused, changing nothing:** cron, single-query / one-shot runs (`HERMES_SINGLE_QUERY_SESSION`, source `oneshot`), kanban workers, `webhook`, `msgraph_webhook`, `api_server`, email, SMS, source `tool`, `gateway`, and **every value not listed above**, including new platforms.

**Known limits.** An empty platform and source is also what a library caller or a delegated sub-agent can carry, and the plugin has no public signal to tell those apart, so layer 2 alone cannot stop them; layer 1 does by default (a CLI sub-agent write is denied unless you opt in with the settings above, and a gateway sub-agent write asks you). A finite (`-q` / `-z`) turn admitted through the gateway daemon also carries no marker the plugin can read; layer 1 covers it.

Read-only tools (`list_availability`, `list_upcoming`) work everywhere and are never gated. The plugin never auto-approves, never changes Hermes' approval settings, and never waits on a prompt of its own, so it cannot hang an unattended run.

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

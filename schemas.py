"""Tool schemas the model reads."""

_CAL = {"type": "string", "description": "Calendar ID. Defaults to the configured calendar (primary)."}
_TZ = {"type": "string", "description": "IANA timezone, e.g. America/Chicago. Defaults to the configured timezone."}
_CONFIRM = {"type": "boolean", "description": "Must be true, and only after the user has explicitly agreed to this exact action."}

LIST_AVAILABILITY = {
    "name": "list_availability",
    "description": "Find genuinely free slots on the user's Google Calendar (FreeBusy). Never guess availability; call this first. Window is capped at 14 days.",
    "parameters": {"type": "object", "properties": {
        "time_min": {"type": "string", "description": "Window start, RFC3339 (e.g. 2026-11-17T09:00:00-06:00) or YYYY-MM-DDTHH:MM in the timezone."},
        "time_max": {"type": "string", "description": "Window end, same formats. At most 14 days after time_min."},
        "duration_minutes": {"type": "integer", "description": "Slot length. Defaults to the configured consult length (30)."},
        "timezone": _TZ, "calendar_id": _CAL},
        "required": ["time_min", "time_max"]},
}

LIST_UPCOMING = {
    "name": "list_upcoming",
    "description": "List upcoming calendar events (id, title, start, end, link, status).",
    "parameters": {"type": "object", "properties": {
        "max_results": {"type": "integer", "description": "Default 10, maximum 25."},
        "time_min": {"type": "string", "description": "Only events after this time (RFC3339). Defaults to now."},
        "calendar_id": _CAL}},
}

BOOK_EVENT = {
    "name": "book_event",
    "description": "Book a consult on the calendar (e.g. 'Strategy consult'). Re-checks FreeBusy and refuses on conflict. Requires confirm=true after the user agrees to the exact time.",
    "parameters": {"type": "object", "properties": {
        "title": {"type": "string", "description": "Event title, e.g. 'Strategy consult'."},
        "start": {"type": "string", "description": "Start, RFC3339 or YYYY-MM-DDTHH:MM in the timezone."},
        "end": {"type": "string", "description": "End. Optional: defaults to start plus the consult length."},
        "timezone": _TZ,
        "description": {"type": "string"},
        "attendees": {"type": "array", "items": {"type": "string"}, "description": "Attendee email addresses (invitations are sent)."},
        "calendar_id": _CAL, "confirm": _CONFIRM},
        "required": ["title", "start", "confirm"]},
}

RESCHEDULE_EVENT = {
    "name": "reschedule_event",
    "description": "Move an existing event to a new free time. Re-checks FreeBusy (ignoring the event itself). Requires confirm=true.",
    "parameters": {"type": "object", "properties": {
        "event_id": {"type": "string"}, "start": {"type": "string"},
        "end": {"type": "string", "description": "Optional: keeps the original length when omitted."},
        "timezone": _TZ, "calendar_id": _CAL, "confirm": _CONFIRM},
        "required": ["event_id", "start", "confirm"]},
}

CANCEL_EVENT = {
    "name": "cancel_event",
    "description": "Cancel (delete) a calendar event by id. Requires confirm=true after the user agrees.",
    "parameters": {"type": "object", "properties": {
        "event_id": {"type": "string"}, "calendar_id": _CAL, "confirm": _CONFIRM},
        "required": ["event_id", "confirm"]},
}

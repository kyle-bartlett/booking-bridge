"""Tool handlers: args dict in, JSON string out, never raise."""

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone as dt_tz
from zoneinfo import ZoneInfo

from . import calendar_api as api

MAX_WINDOW_DAYS = 14
DEFAULTS = {"default_calendar": "primary", "default_timezone": "America/Chicago", "default_duration_minutes": 30}
_UNATTENDED_PLATFORMS = {"webhook", "msgraph_webhook", "api_server"}


def status_text() -> str:
    """Text for the /booking status command."""
    try:
        r = json.loads(list_upcoming({"max_results": 5}))
    except Exception as exc:  # pragma: no cover
        return f"booking-bridge: could not read calendar ({type(exc).__name__})."
    if not r.get("ok"):
        return "booking-bridge: " + str(r.get("error"))
    lines = ["booking-bridge: signed in to Google Calendar. Next events:"]
    lines += [f"- {e['start']}  {e['title']}" for e in r["events"]] or ["- none upcoming"]
    return "\n".join(lines)


def _out(**kw) -> str:
    return json.dumps(kw, default=str)


def _err(msg: str, **kw) -> str:
    return _out(ok=False, error=msg, **kw)


_CTX = None  # the PluginContext, bound once by register()


def bind(ctx) -> None:
    global _CTX
    _CTX = ctx


def _setting(name: str, kwargs: dict):
    """Configured value (plugins.entries.booking-bridge.settings), else the manifest default."""
    try:
        if _CTX is not None:
            val = _CTX.get_config(name, None)
            if val not in (None, ""):
                return val
    except Exception:
        pass
    return DEFAULTS[name]


def _session_env(name: str) -> str:
    try:
        from gateway.session_context import get_session_env  # documented session accessor
        return get_session_env(name, "") or ""
    except Exception:
        return os.environ.get(name, "")


def _truthy(v: str) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "on")


# Allowlist, not denylist: anything not named here (unknown plugin platforms, kanban, email, sms, relay, ...) fails closed.
_LOCAL_SURFACES = {"", "local", "cli", "tui", "desktop", "acp", "gateway"}
_HUMAN_CHAT_PLATFORMS = {"telegram", "discord", "slack", "whatsapp", "whatsapp_cloud", "signal", "mattermost",
                         "matrix", "bluebubbles"}


def _unattended():
    """Reason string when we cannot show a person is present to approve a calendar change, else None.

    Allowed only on a local interactive surface (CLI, TUI, Desktop, ACP) or a named human chat platform. Cron,
    single-query / one-shot runs, kanban workers, webhook-style platforms and every unrecognized platform or
    source are refused. The user's explicit agreement in the live conversation is what confirm=true records.
    """
    try:
        if _CTX is not None and _CTX.current_cron_execution() is not None:
            return "a scheduled cron run"
    except Exception:
        pass
    if _truthy(_session_env("HERMES_CRON_SESSION")):
        return "a scheduled cron run"
    if _truthy(_session_env("HERMES_SINGLE_QUERY_SESSION")):
        return "a single-query (-q) run"
    if _session_env("HERMES_KANBAN_TASK"):
        return "a kanban worker"
    platform = _session_env("HERMES_SESSION_PLATFORM").strip().lower()
    source = _session_env("HERMES_SESSION_SOURCE").strip().lower()
    if platform not in _LOCAL_SURFACES and platform not in _HUMAN_CHAT_PLATFORMS:
        return f"an unrecognized or unattended platform ({platform})"
    if source not in _LOCAL_SURFACES and source not in _HUMAN_CHAT_PLATFORMS:
        return f"an unrecognized or unattended session source ({source})"
    return None



WRITE_TOOLS = ("book_event", "reschedule_event", "cancel_event")


def approval_directive(tool_name: str = "", args=None, **kwargs):
    """``pre_tool_call`` hook: send every calendar write to Hermes's own human-approval gate.

    Returns ``{"action": "approve", ...}`` for the write tools (public hook contract). Hermes then asks the
    person for Once / Session / Always, and fails the call closed wherever nobody can answer: cron, ``-q`` /
    ``-z`` one-shot runs (including ones admitted through the gateway daemon), webhook-style platforms. Read-only
    tools are untouched. Never raises: a malformed call still gets an approval request.
    """
    try:
        if tool_name not in WRITE_TOOLS:
            return None
        a = args if isinstance(args, dict) else {}
        what = {
            "book_event": lambda: f"Book \"{a.get('title', '')}\" on {a.get('start', '?')} to {a.get('end', '?')}",
            "reschedule_event": lambda: f"Move event {a.get('event_id', '?')} to {a.get('start', '?')} - {a.get('end', '?')}",
            "cancel_event": lambda: f"Cancel (delete) calendar event {a.get('event_id', '?')}",
        }[tool_name]()
        if tool_name == "book_event" and a.get("attendees"):
            what += f" (invites: {', '.join(str(x) for x in a['attendees'][:5])})"
        key = hashlib.sha256(json.dumps(a, sort_keys=True, default=str).encode()).hexdigest()[:16]
        return {"action": "approve", "message": f"booking-bridge: {what} on Google Calendar",
                "rule_key": f"booking-bridge:{tool_name}:{key}"}
    except Exception:
        return {"action": "approve", "message": f"booking-bridge: {tool_name} changes your Google Calendar",
                "rule_key": f"booking-bridge:{tool_name}"}


def _write_guard(args: dict):
    if args.get("confirm") is not True:
        return _err("Not done: confirm must be true, and only after the user explicitly agrees to this exact action.")
    why = _unattended()
    if why:
        return _err(f"Not done: this is {why}, so nobody can approve a calendar change. Run it from an interactive session.")
    return None


def _parse(value: str, tz: ZoneInfo) -> datetime:
    dt = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt


def _zone(args: dict, kwargs: dict) -> ZoneInfo:
    return ZoneInfo(args.get("timezone") or _setting("default_timezone", kwargs))


def _rfc(dt: datetime) -> str:
    return dt.isoformat()


def _busy_intervals(busy: list) -> list:
    return sorted((_parse(b["start"], dt_tz.utc), _parse(b["end"], dt_tz.utc)) for b in busy)


def _free_slots(start: datetime, end: datetime, busy: list, minutes: int) -> list:
    """Free windows of at least `minutes`, cut into back-to-back slots of that length."""
    step, slots, cursor = timedelta(minutes=minutes), [], start
    for b_start, b_end in _busy_intervals(busy) + [(end, end)]:
        while cursor + step <= min(b_start, end):
            slots.append((cursor, cursor + step))
            cursor += step
        cursor = max(cursor, b_end)
    return slots


def _slim(ev: dict) -> dict:
    return {"event_id": ev.get("id"), "title": ev.get("summary", ""),
            "start": (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date"),
            "end": (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date"),
            "htmlLink": ev.get("htmlLink"), "status": ev.get("status")}


def list_availability(args: dict, **kwargs) -> str:
    try:
        tz = _zone(args, kwargs)
        cal = args.get("calendar_id") or _setting("default_calendar", kwargs)
        minutes = int(args.get("duration_minutes") or _setting("default_duration_minutes", kwargs))
        if minutes < 5 or minutes > 480:
            return _err("duration_minutes must be between 5 and 480.")
        t0, t1 = _parse(args["time_min"], tz), _parse(args["time_max"], tz)
        if t1 <= t0:
            return _err("time_max must be after time_min.")
        if t1 - t0 > timedelta(days=MAX_WINDOW_DAYS):
            return _err(f"Window too large. Ask for at most {MAX_WINDOW_DAYS} days at a time.")
        busy = api.free_busy(_rfc(t0), _rfc(t1), str(tz), cal)
        slots = _free_slots(t0, t1, busy, minutes)
        return _out(ok=True, calendar_id=cal, timezone=str(tz), duration_minutes=minutes,
                    slots=[{"start": _rfc(s.astimezone(tz)), "end": _rfc(e.astimezone(tz))} for s, e in slots[:60]],
                    truncated=len(slots) > 60)
    except api.CalendarError as exc:
        return _err(str(exc))
    except KeyError as exc:
        return _err(f"Missing argument: {exc.args[0]}")
    except Exception as exc:
        return _err(f"Could not list availability: {type(exc).__name__}: {exc}")


def list_upcoming(args: dict, **kwargs) -> str:
    try:
        cal = args.get("calendar_id") or _setting("default_calendar", kwargs)
        n = max(1, min(int(args.get("max_results") or 10), 25))
        tmin = args.get("time_min") or datetime.now(dt_tz.utc).isoformat()
        if args.get("time_min"):
            tmin = _rfc(_parse(args["time_min"], ZoneInfo(_setting("default_timezone", kwargs))))
        events = api.list_events(cal, tmin, n)
        return _out(ok=True, calendar_id=cal, events=[_slim(e) for e in events[:n]])
    except api.CalendarError as exc:
        return _err(str(exc))
    except Exception as exc:
        return _err(f"Could not list events: {type(exc).__name__}: {exc}")


def _key(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:32]


def book_event(args: dict, **kwargs) -> str:
    try:
        blocked = _write_guard(args)
        if blocked:
            return blocked
        tz = _zone(args, kwargs)
        cal = args.get("calendar_id") or _setting("default_calendar", kwargs)
        t0 = _parse(args["start"], tz)
        t1 = _parse(args["end"], tz) if args.get("end") else t0 + timedelta(minutes=int(_setting("default_duration_minutes", kwargs)))
        if t1 <= t0:
            return _err("end must be after start.")
        if t0 < datetime.now(dt_tz.utc):
            return _err("That start time is in the past.")
        title = str(args["title"]).strip()[:200]
        attendees = [str(a).strip() for a in (args.get("attendees") or []) if "@" in str(a)]
        idem = _key(cal, title, _rfc(t0.astimezone(dt_tz.utc)), _rfc(t1.astimezone(dt_tz.utc)), ",".join(sorted(attendees)))
        existing = [e for e in api.list_events(cal, _rfc(t0 - timedelta(minutes=1)), 10)
                    if ((e.get("extendedProperties") or {}).get("private") or {}).get("bookingBridgeKey") == idem]
        if existing:
            return _out(ok=True, duplicate=True, note="Already booked; nothing new created.", **_slim(existing[0]))
        busy = api.free_busy(_rfc(t0), _rfc(t1), str(tz), cal)
        if busy:
            return _err("That time is no longer free. Nothing was booked.",
                        conflicts=[{"start": b["start"], "end": b["end"]} for b in busy])
        body = {"summary": title, "start": {"dateTime": _rfc(t0), "timeZone": str(tz)},
                "end": {"dateTime": _rfc(t1), "timeZone": str(tz)},
                "extendedProperties": {"private": {"bookingBridgeKey": idem}}}
        if args.get("description"):
            body["description"] = str(args["description"])[:4000]
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        ev = api.insert_event(cal, body)
        return _out(ok=True, **_slim(ev))
    except api.CalendarError as exc:
        return _err(str(exc))
    except KeyError as exc:
        return _err(f"Missing argument: {exc.args[0]}")
    except Exception as exc:
        return _err(f"Could not book: {type(exc).__name__}: {exc}")


def reschedule_event(args: dict, **kwargs) -> str:
    try:
        blocked = _write_guard(args)
        if blocked:
            return blocked
        tz = _zone(args, kwargs)
        cal = args.get("calendar_id") or _setting("default_calendar", kwargs)
        eid = str(args["event_id"])
        ev = api.get_event(cal, eid)
        old0 = _parse(ev["start"]["dateTime"], tz)
        old1 = _parse(ev["end"]["dateTime"], tz)
        t0 = _parse(args["start"], tz)
        t1 = _parse(args["end"], tz) if args.get("end") else t0 + (old1 - old0)
        if t1 <= t0:
            return _err("end must be after start.")
        busy = [b for b in api.free_busy(_rfc(t0), _rfc(t1), str(tz), cal)
                if not (_parse(b["start"], dt_tz.utc) == old0.astimezone(dt_tz.utc)
                        and _parse(b["end"], dt_tz.utc) == old1.astimezone(dt_tz.utc))]
        if busy:
            return _err("That time is not free. Nothing was moved.",
                        conflicts=[{"start": b["start"], "end": b["end"]} for b in busy])
        out = api.patch_event(cal, eid, {"start": {"dateTime": _rfc(t0), "timeZone": str(tz)},
                                         "end": {"dateTime": _rfc(t1), "timeZone": str(tz)}})
        return _out(ok=True, **_slim(out))
    except api.CalendarError as exc:
        return _err(str(exc))
    except KeyError as exc:
        return _err(f"Missing argument or event field: {exc.args[0]}")
    except Exception as exc:
        return _err(f"Could not reschedule: {type(exc).__name__}: {exc}")


def cancel_event(args: dict, **kwargs) -> str:
    try:
        blocked = _write_guard(args)
        if blocked:
            return blocked
        cal = args.get("calendar_id") or _setting("default_calendar", kwargs)
        eid = str(args["event_id"])
        ev = api.get_event(cal, eid)
        api.delete_event(cal, eid)
        return _out(ok=True, cancelled=True, event_id=eid, title=ev.get("summary", ""))
    except api.CalendarError as exc:
        return _err(str(exc))
    except KeyError as exc:
        return _err(f"Missing argument: {exc.args[0]}")
    except Exception as exc:
        return _err(f"Could not cancel: {type(exc).__name__}: {exc}")

"""Google Calendar v3 calls. Every request goes through Hermes' credentialed_provider_request."""

from urllib.parse import quote

from hermes_cli.auth_constants import AuthError
from hermes_cli.plugin_provider_requests import ProviderNotSignedIn, credentialed_provider_request

BASE = "https://www.googleapis.com/calendar/v3"
SIGN_IN = "hermes auth add booking-bridge:google"


class CalendarError(Exception):
    """A user-presentable failure (never carries tokens)."""


def call(method: str, path: str, json=None):
    try:
        resp = credentialed_provider_request("google", method, BASE + path, json=json, timeout=20)
    except ProviderNotSignedIn:
        raise CalendarError(f"Not signed in to Google. Run: {SIGN_IN}")
    except AuthError as exc:
        code = getattr(exc, "code", "auth_error")
        if code in ("oauth_client_id_missing", "invalid_client"):
            raise CalendarError("The Google OAuth client is not set up. Set BOOKING_BRIDGE_CLIENT_ID and "
                                f"BOOKING_BRIDGE_CLIENT_SECRET (Desktop app client), then run: {SIGN_IN}")
        raise CalendarError(f"Google auth problem ({code}). Run: {SIGN_IN}")
    except PermissionError as exc:
        raise CalendarError(f"Request refused by Hermes: {exc}")
    except Exception as exc:  # network etc.; message only, no traceback
        raise CalendarError(f"Google Calendar request failed: {type(exc).__name__}")
    if resp.status == 204:
        return {}
    try:
        data = resp.json()
    except Exception:
        data = {}
    if resp.status >= 300:
        msg = (data.get("error", {}) or {}).get("message", "") if isinstance(data, dict) else ""
        raise CalendarError(f"Google Calendar returned HTTP {resp.status}. {msg}".strip())
    return data


def cal_path(calendar_id: str) -> str:
    return "/calendars/" + quote(calendar_id, safe="")


def free_busy(time_min: str, time_max: str, tz: str, calendar_id: str) -> list:
    data = call("POST", "/freeBusy", {"timeMin": time_min, "timeMax": time_max, "timeZone": tz,
                                      "items": [{"id": calendar_id}]})
    cal = (data.get("calendars") or {}).get(calendar_id)
    if cal is None:
        cal = next(iter((data.get("calendars") or {}).values()), None)
    if cal is None or cal.get("errors"):
        raise CalendarError("Google could not return availability for that calendar.")
    return cal.get("busy", [])


def list_events(calendar_id: str, time_min: str, max_results: int) -> list:
    q = f"?singleEvents=true&orderBy=startTime&maxResults={int(max_results)}&timeMin={quote(time_min, safe='')}"
    return call("GET", cal_path(calendar_id) + "/events" + q).get("items", [])


def get_event(calendar_id: str, event_id: str) -> dict:
    return call("GET", cal_path(calendar_id) + "/events/" + quote(event_id, safe=""))


def insert_event(calendar_id: str, body: dict) -> dict:
    return call("POST", cal_path(calendar_id) + "/events?sendUpdates=all", body)


def patch_event(calendar_id: str, event_id: str, body: dict) -> dict:
    return call("PATCH", cal_path(calendar_id) + "/events/" + quote(event_id, safe="") + "?sendUpdates=all", body)


def delete_event(calendar_id: str, event_id: str) -> dict:
    return call("DELETE", cal_path(calendar_id) + "/events/" + quote(event_id, safe="") + "?sendUpdates=all")

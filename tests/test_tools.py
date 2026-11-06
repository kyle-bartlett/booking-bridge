import json
import os
import sys
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

# Stub the Hermes modules when running outside Hermes.
try:
    import hermes_cli.plugin_provider_requests  # noqa: F401
except Exception:
    m1 = types.ModuleType("hermes_cli"); m2 = types.ModuleType("hermes_cli.plugin_provider_requests")
    m3 = types.ModuleType("hermes_cli.auth_constants")
    class _NS(RuntimeError): pass
    class _AE(Exception): code = "x"
    m2.ProviderNotSignedIn = _NS; m2.credentialed_provider_request = lambda *a, **k: None
    m3.AuthError = _AE
    sys.modules.update({"hermes_cli": m1, "hermes_cli.plugin_provider_requests": m2, "hermes_cli.auth_constants": m3})

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
pkg = Path(__file__).resolve().parents[1].name
tools = __import__(pkg + ".tools", fromlist=["x"])
api = __import__(pkg + ".calendar_api", fromlist=["x"])
init = __import__(pkg, fromlist=["x"])

ENVKEYS = ("HERMES_CRON_SESSION", "HERMES_SINGLE_QUERY_SESSION", "HERMES_SESSION_PLATFORM", "HERMES_SESSION_SOURCE", "HERMES_KANBAN_TASK")
NEXT = (datetime.now(timezone.utc) + timedelta(days=3)).replace(hour=15, minute=0, second=0, microsecond=0)
iso = lambda d: d.isoformat()


class T(unittest.TestCase):
    def test_slots_skip_busy(self):
        busy = [{"start": iso(NEXT + timedelta(minutes=30)), "end": iso(NEXT + timedelta(minutes=60))}]
        with mock.patch.object(api, "free_busy", return_value=busy):
            r = json.loads(tools.list_availability({"time_min": iso(NEXT), "time_max": iso(NEXT + timedelta(hours=2))}))
        starts = [datetime.fromisoformat(s["start"]).astimezone(timezone.utc).isoformat() for s in r["slots"]]
        self.assertEqual(len(starts), 3)
        self.assertNotIn(iso(NEXT + timedelta(minutes=30)), starts)

    def test_window_cap(self):
        r = json.loads(tools.list_availability({"time_min": iso(NEXT), "time_max": iso(NEXT + timedelta(days=30))}))
        self.assertFalse(r["ok"])

    def test_api_failure_no_invented_times(self):
        with mock.patch.object(api, "free_busy", side_effect=api.CalendarError("Not signed in. Run: hermes auth add booking-bridge:google")):
            r = json.loads(tools.list_availability({"time_min": iso(NEXT), "time_max": iso(NEXT + timedelta(hours=2))}))
        self.assertFalse(r["ok"]); self.assertNotIn("slots", r); self.assertIn("hermes auth add booking-bridge:google", r["error"])

    def test_book_requires_confirm(self):
        r = json.loads(tools.book_event({"title": "Strategy consult", "start": iso(NEXT)}))
        self.assertFalse(r["ok"])

    def test_book_conflict_no_insert(self):
        with mock.patch.object(api, "list_events", return_value=[]), \
             mock.patch.object(api, "free_busy", return_value=[{"start": iso(NEXT), "end": iso(NEXT + timedelta(minutes=30))}]), \
             mock.patch.object(api, "insert_event") as ins:
            r = json.loads(tools.book_event({"title": "Strategy consult", "start": iso(NEXT), "confirm": True}))
        self.assertFalse(r["ok"]); ins.assert_not_called()

    def test_book_success_and_duplicate(self):
        ev = {"id": "e1", "summary": "Strategy consult", "start": {"dateTime": iso(NEXT)}, "end": {"dateTime": iso(NEXT)}, "htmlLink": "l", "status": "confirmed"}
        with mock.patch.object(api, "list_events", return_value=[]), mock.patch.object(api, "free_busy", return_value=[]), \
             mock.patch.object(api, "insert_event", return_value=ev) as ins:
            r = json.loads(tools.book_event({"title": "Strategy consult", "start": iso(NEXT), "confirm": True}))
            self.assertTrue(r["ok"]); self.assertEqual(r["event_id"], "e1")
            key = ins.call_args[0][1]["extendedProperties"]["private"]["bookingBridgeKey"]
        dup = dict(ev, extendedProperties={"private": {"bookingBridgeKey": key}})
        with mock.patch.object(api, "list_events", return_value=[dup]), mock.patch.object(api, "insert_event") as ins2:
            r = json.loads(tools.book_event({"title": "Strategy consult", "start": iso(NEXT), "confirm": True}))
        self.assertTrue(r["duplicate"]); ins2.assert_not_called()

    def _write_all(self):
        out = []
        with mock.patch.object(api, "get_event", return_value={"summary": "x", "start": {"dateTime": iso(NEXT)}, "end": {"dateTime": iso(NEXT)}}), \
             mock.patch.object(api, "delete_event") as d, mock.patch.object(api, "insert_event") as i, \
             mock.patch.object(api, "patch_event") as p, mock.patch.object(api, "list_events", return_value=[]), \
             mock.patch.object(api, "free_busy", return_value=[]):
            out.append(json.loads(tools.cancel_event({"event_id": "e1", "confirm": True})))
            out.append(json.loads(tools.book_event({"title": "t", "start": iso(NEXT), "confirm": True})))
            out.append(json.loads(tools.reschedule_event({"event_id": "e1", "start": iso(NEXT), "confirm": True})))
            touched = d.called or i.called or p.called
        return out, touched

    def test_unattended_contexts_fail_closed(self):
        clean = {k: "" for k in ENVKEYS}
        for label, env in (("kanban", {"HERMES_KANBAN_TASK": "t1"}), ("oneshot source", {"HERMES_SESSION_SOURCE": "oneshot"}),
                           ("unknown platform", {"HERMES_SESSION_PLATFORM": "some_new_plugin_platform"}),
                           ("email", {"HERMES_SESSION_PLATFORM": "email"}),
                           ("unknown source", {"HERMES_SESSION_SOURCE": "automation"}),("cron", {"HERMES_CRON_SESSION": "1"}), ("single-query", {"HERMES_SINGLE_QUERY_SESSION": "1"}),
                           ("webhook", {"HERMES_SESSION_PLATFORM": "webhook"}),
                           ("msgraph_webhook", {"HERMES_SESSION_PLATFORM": "msgraph_webhook"}),
                           ("api_server", {"HERMES_SESSION_PLATFORM": "api_server"})):
            with self.subTest(label), mock.patch.dict(os.environ, dict(clean, **env)):
                out, touched = self._write_all()
                self.assertTrue(all(not r["ok"] for r in out)); self.assertFalse(touched)

    def test_cron_execution_object_fails_closed(self):
        tools.bind(types.SimpleNamespace(current_cron_execution=lambda: object(), get_config=lambda k, d=None: d))
        try:
            out, touched = self._write_all()
            self.assertTrue(all(not r["ok"] for r in out)); self.assertFalse(touched)
        finally:
            tools.bind(None)

    def test_interactive_and_chat_gateway_allowed(self):
        clean = {k: "" for k in ENVKEYS}
        for platform in ("", "cli", "local", "telegram", "slack"):
            with self.subTest(platform), mock.patch.dict(os.environ, dict(clean, HERMES_SESSION_PLATFORM=platform)):
                out, touched = self._write_all()
                self.assertTrue(touched)

    def test_settings_from_ctx(self):
        tools.bind(types.SimpleNamespace(current_cron_execution=lambda: None,
                                         get_config=lambda k, d=None: {"default_calendar": "team@x"}.get(k, d)))
        try:
            self.assertEqual(tools._setting("default_calendar", {}), "team@x")
            self.assertEqual(tools._setting("default_duration_minutes", {}), 30)
        finally:
            tools.bind(None)

    def test_status_command(self):
        with mock.patch.object(api, "list_events", return_value=[]):
            self.assertIn("signed in", tools.status_text())
        with mock.patch.object(api, "list_events", side_effect=api.CalendarError("Not signed in. Run: hermes auth add booking-bridge:google")):
            self.assertIn("hermes auth add booking-bridge:google", tools.status_text())

    def test_cancel(self):
        with mock.patch.object(api, "get_event", return_value={"summary": "x"}), mock.patch.object(api, "delete_event") as d:
            r = json.loads(tools.cancel_event({"event_id": "e1", "confirm": True}))
        self.assertTrue(r["cancelled"]); d.assert_called_once()

    def test_list_upcoming_cap(self):
        with mock.patch.object(api, "list_events", return_value=[]) as le:
            tools.list_upcoming({"max_results": 999})
        self.assertEqual(le.call_args[0][2], 25)

    def test_register_matches_manifest(self):
        names = []
        extra = []
        ctx = types.SimpleNamespace(register_tool=lambda **k: names.append(k["name"]),
                                    register_command=lambda *a, **k: extra.append("cmd"),
                                    register_skill=lambda *a, **k: extra.append("skill"),
                                    get_config=lambda k, d=None: d, current_cron_execution=lambda: None)
        init.register(ctx)
        self.assertEqual(extra, ["cmd", "skill"])
        manifest = (Path(__file__).resolve().parents[1] / "plugin.yaml").read_text()
        for n in names:
            self.assertIn("  - " + n, manifest)
        self.assertEqual(len(names), 5)

    def test_not_signed_in_names_command(self):
        with mock.patch.object(api, "credentialed_provider_request", side_effect=api.ProviderNotSignedIn("x")):
            r = json.loads(tools.list_availability({"time_min": iso(NEXT), "time_max": iso(NEXT + timedelta(hours=2))}))
        self.assertFalse(r["ok"]); self.assertIn("hermes auth add booking-bridge:google", r["error"])

    def test_reschedule_moves_when_free_and_blocks_when_busy(self):
        ev = {"start": {"dateTime": iso(NEXT)}, "end": {"dateTime": iso(NEXT + timedelta(minutes=30))}}
        args = {"event_id": "e1", "start": iso(NEXT + timedelta(hours=2)), "confirm": True}
        with mock.patch.object(api, "get_event", return_value=ev), mock.patch.object(api, "free_busy", return_value=[]), \
                mock.patch.object(api, "patch_event", return_value={"id": "e1"}) as p:
            r = json.loads(tools.reschedule_event(args))
        self.assertTrue(r["ok"]); p.assert_called_once()
        busy = [{"start": iso(NEXT + timedelta(hours=2)), "end": iso(NEXT + timedelta(hours=3))}]
        with mock.patch.object(api, "get_event", return_value=ev), mock.patch.object(api, "free_busy", return_value=busy), \
                mock.patch.object(api, "patch_event") as p2:
            r = json.loads(tools.reschedule_event(args))
        self.assertFalse(r["ok"]); p2.assert_not_called()

    def test_skill_registered(self):
        calls = []
        ctx = types.SimpleNamespace(register_tool=lambda **k: None, register_command=lambda *a, **k: None,
                                    register_skill=lambda *a, **k: calls.append(a),
                                    get_config=lambda k, d=None: d, current_cron_execution=lambda: None)
        init.register(ctx)
        self.assertEqual(calls[0][0], "consult-booking")


if __name__ == "__main__":
    unittest.main()

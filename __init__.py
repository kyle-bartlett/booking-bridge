"""Booking Bridge: Google Calendar consult booking for Hermes."""

from pathlib import Path

from . import schemas, tools


def register(ctx):
    tools.bind(ctx)
    for name, schema, handler in (
        ("list_availability", schemas.LIST_AVAILABILITY, tools.list_availability),
        ("list_upcoming", schemas.LIST_UPCOMING, tools.list_upcoming),
        ("book_event", schemas.BOOK_EVENT, tools.book_event),
        ("reschedule_event", schemas.RESCHEDULE_EVENT, tools.reschedule_event),
        ("cancel_event", schemas.CANCEL_EVENT, tools.cancel_event),
    ):
        ctx.register_tool(name=name, toolset="booking-bridge", schema=schema, handler=handler)

    def booking_command(raw_args: str = "") -> str:
        if (raw_args or "status").strip().lower() in ("", "status"):
            return tools.status_text()
        return "Usage: /booking status"

    ctx.register_hook("pre_tool_call", tools.approval_directive)

    ctx.register_command("booking", booking_command, description="Show Google sign-in state and next events",
                         args_hint="status")
    skill = Path(__file__).parent / "skills" / "consult-booking" / "SKILL.md"
    if skill.exists():
        ctx.register_skill("consult-booking", skill, description="Book a strategy consult with the booking-bridge tools")

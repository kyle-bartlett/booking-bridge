"""Booking Bridge: Google Calendar consult booking for Hermes."""

from . import schemas, tools


def register(ctx):
    for name, schema, handler in (
        ("list_availability", schemas.LIST_AVAILABILITY, tools.list_availability),
        ("list_upcoming", schemas.LIST_UPCOMING, tools.list_upcoming),
        ("book_event", schemas.BOOK_EVENT, tools.book_event),
        ("reschedule_event", schemas.RESCHEDULE_EVENT, tools.reschedule_event),
        ("cancel_event", schemas.CANCEL_EVENT, tools.cancel_event),
    ):
        ctx.register_tool(name=name, toolset="booking-bridge", schema=schema, handler=handler)

    from pathlib import Path

    skill = Path(__file__).parent / "skills" / "consult-booking" / "SKILL.md"
    if skill.exists() and hasattr(ctx, "register_skill"):
        ctx.register_skill("consult-booking", skill, description="Book a strategy consult with the booking-bridge tools.")

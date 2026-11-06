---
name: consult-booking
description: Book a strategy consult on Google Calendar with the booking-bridge tools.
---

0. Never guess slots or hours. Speak times in the user's timezone.
1. Call `list_availability` for the window the user names (max 14 days). Offer only slots it returns.
2. Read the exact time back to the user and wait for a clear yes.
3. Call `book_event` with `confirm: true`. If it reports a conflict, go back to step 1.
4. To change or cancel, use `reschedule_event` / `cancel_event` the same way (look up ids with `list_upcoming`).

If a tool says Google is not signed in, tell the user to run `hermes auth add booking-bridge:google`.

"""Match predicates against individual, decoded CalDAV events."""

from __future__ import annotations

from icalendar import Calendar

from webarena_pro_core.eval.predicate import match_entry
from webarena_pro_core.eval.providers.dav import report_data


def matches_calendar_event(xml: str, predicate: dict) -> tuple[bool, str]:
    """Require one active VEVENT to satisfy every predicate condition.

    Parse DAV and iCalendar rather than matching the XML wire representation:
    XML entities, line folding, and escaped TEXT values are serialization, not
    task content. A malformed report raises so the backend probe is inconclusive.
    """
    records = report_data(xml, "{urn:ietf:params:xml:ns:caldav}calendar-data")
    count = 0
    for record in records:
        for event in Calendar.from_ical(record).walk("VEVENT"):
            if str(event.get("STATUS", "")).upper() == "CANCELLED":
                continue
            count += 1
            summary = str(event.get("SUMMARY", ""))
            description = str(event.get("DESCRIPTION", ""))
            start = event.get("DTSTART")
            value = start.dt if start is not None else None
            # For timed events, retain the calendar's local date rather than
            # moving midnight across a boundary by converting to UTC.
            day = value.date() if hasattr(value, "date") else value
            attrs = {
                "summary": summary,
                "description": description,
                "text": summary + "\n" + description,
                "date": day.isoformat() if day is not None else "",
            }
            if match_entry(str(event.get("UID", "")), attrs, predicate):
                return True, "one active calendar event matched all conditions"
    return False, f"no matching active calendar event among {count} events"

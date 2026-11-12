"""CalDAV event snapshot provider (NextCloud Calendar).

Sends a REPORT query to the user's personal calendar, parses each VEVENT
via ``icalendar``, and returns a Snapshot keyed by VEVENT UID.
"""

from __future__ import annotations

import icalendar
import requests

from webarena_pro_core.eval.defaults import (
    DEPLOYED_WEBSITE_URLS,
    WEBSITE_CREDENTIALS,
)
from webarena_pro_core.eval.providers import SnapshotProvider
from webarena_pro_core.eval.providers.dav import report_data
from webarena_pro_core.eval.snapshot import Snapshot


_CALENDAR_QUERY = (
    '<?xml version="1.0"?>'
    '<c:calendar-query xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:d="DAV:">'
    "<d:prop><c:calendar-data/></d:prop>"
    '<c:filter><c:comp-filter name="VCALENDAR">'
    '<c:comp-filter name="VEVENT"/>'
    "</c:comp-filter></c:filter>"
    "</c:calendar-query>"
)


class CalDAVEventsProvider(SnapshotProvider):
    """Snapshot VEVENTs from a user's personal calendar.

    params:
        user (str)
        calendar (str, optional): calendar name (default "personal")
    """

    def fetch(self, site: str, params: dict) -> Snapshot:
        user = params["user"]
        calendar = params.get("calendar", "personal")
        base = DEPLOYED_WEBSITE_URLS[site]
        url = f"{base}/remote.php/dav/calendars/{user}/{calendar}/"
        auth = _get_auth(site, user)

        resp = requests.request(
            "REPORT",
            url,
            auth=auth,
            headers={"Depth": "1", "Content-Type": "application/xml"},
            data=_CALENDAR_QUERY,
            timeout=30,
        )
        resp.raise_for_status()

        entries: dict[str, dict] = {}
        for cal_data in _extract_calendar_data(resp.text):
            cal = icalendar.Calendar.from_ical(cal_data)
            for component in cal.walk():
                if component.name != "VEVENT":
                    continue
                uid = str(component.get("UID", "")) or None
                if not uid:
                    raise ValueError("CalDAV event has no UID")
                summary = str(component.get("SUMMARY", "") or "")
                dtstart = component.get("DTSTART")
                dtend = component.get("DTEND")
                entries[uid] = {
                    "summary": summary,
                    "dtstart": _format_dt(dtstart),
                    "dtend": _format_dt(dtend),
                    # Use a pseudo-etag of summary|dtstart so unchanged events
                    # don't show up as "changed" across fetches.
                    "etag": f"{summary}|{_format_dt(dtstart)}",
                }
        return Snapshot(entries=entries)


def _extract_calendar_data(xml: str) -> list[str]:
    return report_data(xml, "{urn:ietf:params:xml:ns:caldav}calendar-data")


def _format_dt(value) -> str:
    if value is None:
        return ""
    try:
        return value.to_ical().decode()
    except Exception:
        return str(value)


def _get_auth(site: str, user: str) -> tuple[str, str]:
    creds = WEBSITE_CREDENTIALS.get(site, [])
    for c in creds:
        if c["username"] == user:
            return (c["username"], c["password"])
    raise KeyError(f"No credentials for user '{user}' on site '{site}'")

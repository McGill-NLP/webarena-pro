"""NextCloud activity log snapshot provider.

Fetches the per-user activity feed (file_deleted / file_restored / file_created
/ file_changed / file_moved / ...) from the NextCloud Activity app. Keyed by
``activity_id`` so each event is unique and diffs cleanly.

Used by Task 100 to verify that an actual delete+restore happened - pure
state-diff on files can't distinguish "agent did nothing" from "agent deleted
everything and restored it perfectly". Activity events close that loophole.
"""

from __future__ import annotations

import requests

from webarena_pro_core.eval.defaults import (
    DEPLOYED_WEBSITE_URLS,
    WEBSITE_CREDENTIALS,
)
from webarena_pro_core.eval.providers import SnapshotProvider
from webarena_pro_core.eval.providers.ocs import response_data
from webarena_pro_core.eval.snapshot import Snapshot


class ActivityLogProvider(SnapshotProvider):
    """Snapshot the most recent file-related activity events for a user.

    params:
        user (str): user whose activity to fetch (auth + filter)
        limit (int, optional): max events to fetch (default 200)
    """

    def fetch(self, site: str, params: dict) -> Snapshot:
        user = params["user"]
        limit = int(params.get("limit", 200))
        base = DEPLOYED_WEBSITE_URLS[site]
        url = f"{base}/ocs/v2.php/apps/activity/api/v2/activity/files"
        auth = _get_auth(site, user)

        resp = requests.get(
            url,
            auth=auth,
            headers={"OCS-APIRequest": "true", "Accept": "application/json"},
            params={"limit": limit, "sort": "desc"},
            timeout=30,
        )
        # Activity's API explicitly uses these statuses for an empty stream.
        # No conditional headers or pagination offset are sent by this provider.
        if resp.status_code in {204, 304}:
            return Snapshot(entries={})
        data = response_data(resp)
        if not isinstance(data, list):
            raise ValueError("OCS activity data is not a list")

        entries: dict[str, dict] = {}
        for event in data:
            aid = event.get("activity_id")
            if aid is None:
                raise ValueError("OCS activity entry has no activity_id")
            entries[str(aid)] = {
                "type": event.get("type", ""),
                "user": event.get("user", ""),
                "subject": event.get("subject", ""),
                "datetime": event.get("datetime", ""),
                # Version key is just the id - activity rows are immutable,
                # so "changed" makes no sense for them.
                "etag": str(aid),
            }
        return Snapshot(entries=entries)


def _get_auth(site: str, user: str) -> tuple[str, str]:
    creds = WEBSITE_CREDENTIALS.get(site, [])
    for c in creds:
        if c["username"] == user:
            return (c["username"], c["password"])
    raise KeyError(f"No credentials for user '{user}' on site '{site}'")

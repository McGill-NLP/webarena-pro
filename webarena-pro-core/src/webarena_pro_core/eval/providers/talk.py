"""NextCloud Talk rooms snapshot provider.

Fetches the list of conversations a user participates in. Attributes include
room type and participants, so tests can assert e.g. "a new 1:1 room with
daniel.brooks was created".
"""

from __future__ import annotations

import requests

from webarena_pro_core.eval.defaults import (
    WEBSITE_CREDENTIALS,
    deployed_website_urls,
)
from webarena_pro_core.eval.providers import SnapshotProvider
from webarena_pro_core.eval.providers.ocs import response_data
from webarena_pro_core.eval.snapshot import Snapshot


class TalkRoomsProvider(SnapshotProvider):
    """Snapshot Talk conversations visible to a user.

    params:
        user (str)
    """

    def fetch(self, site: str, params: dict) -> Snapshot:
        user = params["user"]
        base = deployed_website_urls()[site]
        url = f"{base}/ocs/v2.php/apps/spreed/api/v4/room"
        auth = _get_auth(site, user)
        resp = requests.get(
            url,
            auth=auth,
            headers={"OCS-APIRequest": "true", "Accept": "application/json"},
            timeout=30,
        )
        data = response_data(resp)
        if not isinstance(data, list):
            raise ValueError("OCS Talk rooms data is not a list")

        entries: dict[str, dict] = {}
        for room in data:
            token = room.get("token")
            if not isinstance(token, str) or not token or token in entries:
                raise ValueError("OCS Talk room has a missing or duplicate token")
            # Participants list may live at different keys depending on NC
            # version; grab whatever is present and flatten into a list of
            # user ids.
            participants: list[str] = []
            for key in ("participants", "participantList", "attendees"):
                raw = room.get(key)
                if isinstance(raw, list):
                    for p in raw:
                        if isinstance(p, dict):
                            pid = p.get("actorId") or p.get("userId") or p.get("actor_id")
                            if pid:
                                participants.append(str(pid))
                        elif isinstance(p, str):
                            participants.append(p)
                elif isinstance(raw, dict):
                    participants.extend(str(k) for k in raw.keys())

            entries[token] = {
                "name": room.get("name") or room.get("displayName") or "",
                "type": room.get("type"),
                "participants": participants,
                # Version key: last-activity timestamp so we detect new messages
                # showing up even if room identity is the same.
                "etag": str(room.get("lastActivity", "")),
            }
        return Snapshot(entries=entries)


def fetch_talk_messages(site: str, user: str, token: str) -> list[dict]:
    """One-shot fetch of messages in a room. Not a snapshot provider —
    used by task 106/107 checks that need to inspect message contents of a
    room whose existence has already been verified by a diff.
    """
    base = deployed_website_urls()[site]
    url = f"{base}/ocs/v2.php/apps/spreed/api/v1/chat/{token}"
    auth = _get_auth(site, user)
    resp = requests.get(
        url,
        auth=auth,
        headers={"OCS-APIRequest": "true", "Accept": "application/json"},
        params={"lookIntoFuture": 0, "limit": 100},
        timeout=30,
    )
    data = response_data(resp)
    if not isinstance(data, list):
        raise ValueError("OCS Talk messages data is not a list")
    return data


def _get_auth(site: str, user: str) -> tuple[str, str]:
    creds = WEBSITE_CREDENTIALS.get(site, [])
    for c in creds:
        if c["username"] == user:
            return (c["username"], c["password"])
    raise KeyError(f"No credentials for user '{user}' on site '{site}'")

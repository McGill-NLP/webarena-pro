"""OCS users snapshot provider (NextCloud admin-only).

Fetches the list of user accounts via the OCS provisioning API. Keyed by
username; attributes include email + displayname from a second per-user call
when possible, but falls back to just the username for efficiency.
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


class OCSUsersProvider(SnapshotProvider):
    """Snapshot the set of user accounts on a NextCloud instance.

    params: (none needed - always uses admin auth)
    """

    def fetch(self, site: str, params: dict) -> Snapshot:
        base = DEPLOYED_WEBSITE_URLS[site]
        url = f"{base}/ocs/v2.php/cloud/users"
        auth = _get_admin_auth(site)
        resp = requests.get(
            url,
            auth=auth,
            headers={"OCS-APIRequest": "true", "Accept": "application/json"},
            timeout=30,
        )
        data = response_data(resp)
        if not isinstance(data, dict) or not isinstance(data.get("users"), list):
            raise ValueError("OCS users data has no user list")
        users = data["users"]

        entries: dict[str, dict] = {}
        for uid in users:
            entries[str(uid)] = {
                # Version key is just the uid - we only care about set
                # membership, not per-user content.
                "etag": str(uid),
            }
        return Snapshot(entries=entries)


def _get_admin_auth(site: str) -> tuple[str, str]:
    creds = WEBSITE_CREDENTIALS.get(site, [])
    for c in creds:
        if c["username"] == "admin":
            return (c["username"], c["password"])
    raise KeyError(f"No admin credentials for site '{site}'")

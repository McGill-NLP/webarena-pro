"""CardDAV contacts snapshot provider (NextCloud Contacts).

Fetches VCARDs from a user's addressbook and parses them with ``vobject``.
Used by task 102 to know the expected set of contacts for the emails
spreadsheet.
"""

from __future__ import annotations

import requests
import vobject

from webarena_pro_core.eval.defaults import (
    DEPLOYED_WEBSITE_URLS,
    WEBSITE_CREDENTIALS,
)
from webarena_pro_core.eval.providers import SnapshotProvider
from webarena_pro_core.eval.providers.dav import report_data
from webarena_pro_core.eval.snapshot import Snapshot


_ADDRESSBOOK_QUERY = (
    '<?xml version="1.0"?>'
    '<c:addressbook-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
    "<d:prop><c:address-data/></d:prop>"
    "</c:addressbook-query>"
)


class CardDAVContactsProvider(SnapshotProvider):
    """Snapshot contacts from a user's addressbook.

    params:
        user (str)
        addressbook (str, optional): addressbook name (default "contacts")
    """

    def fetch(self, site: str, params: dict) -> Snapshot:
        user = params["user"]
        addressbook = params.get("addressbook", "contacts")
        base = DEPLOYED_WEBSITE_URLS[site]
        url = f"{base}/remote.php/dav/addressbooks/users/{user}/{addressbook}/"
        auth = _get_auth(site, user)

        resp = requests.request(
            "REPORT",
            url,
            auth=auth,
            headers={"Depth": "1", "Content-Type": "application/xml"},
            data=_ADDRESSBOOK_QUERY,
            timeout=30,
        )
        resp.raise_for_status()

        entries: dict[str, dict] = {}
        for vcard_text in _extract_vcards(resp.text):
            vcard = vobject.readOne(vcard_text)
            uid = getattr(vcard, "uid", None)
            uid_val = uid.value if uid else None
            if not uid_val:
                raise ValueError("CardDAV contact has no UID")
            fn = getattr(vcard, "fn", None)
            fn_val = fn.value if fn else ""
            email = ""
            if hasattr(vcard, "email"):
                email = vcard.email.value
            entries[uid_val] = {
                "fn": fn_val,
                "email": email,
                "etag": f"{fn_val}|{email}",
            }
        return Snapshot(entries=entries)


def _extract_vcards(xml: str) -> list[str]:
    return report_data(xml, "{urn:ietf:params:xml:ns:carddav}address-data")


def _get_auth(site: str, user: str) -> tuple[str, str]:
    creds = WEBSITE_CREDENTIALS.get(site, [])
    for c in creds:
        if c["username"] == user:
            return (c["username"], c["password"])
    raise KeyError(f"No credentials for user '{user}' on site '{site}'")

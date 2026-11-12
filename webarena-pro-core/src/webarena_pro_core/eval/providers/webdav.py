"""WebDAV file tree snapshot provider (NextCloud / ownCloud).

Uses ``webdav4.fsspec.WebdavFileSystem`` for recursive traversal. Optional
Nextcloud identities are read from the same PROPFIND responses.
"""

from __future__ import annotations

from webdav4.fsspec import WebdavFileSystem
from webdav4.client import Client

from webarena_pro_core.eval.defaults import (
    deployed_website_urls,
    WEBSITE_CREDENTIALS,
)
from webarena_pro_core.eval.providers import SnapshotProvider
from webarena_pro_core.eval.snapshot import Snapshot


class _IdentityClient(Client):
    """Retain Nextcloud's stable file IDs from the same directory requests."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_ids = {}

    def propfind(self, path, data=None, headers=None, follow_redirects=False):
        data = data or (
            '<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">'
            '<d:prop><d:resourcetype/><d:getetag/><d:getcontentlength/>'
            '<oc:fileid/></d:prop></d:propfind>'
        )
        result = super().propfind(path, data=data, headers={
            "Content-Type": "application/xml", **(headers or {})
        }, follow_redirects=follow_redirects)
        if result.tree.tag != "{DAV:}multistatus":
            raise ValueError("Nextcloud snapshot is not a DAV multistatus")
        result.get_response_for_path(self.base_url.path, path)
        for response in result.responses.values():
            # Only a successful property response establishes object identity.
            ids = []
            for propstat in response.response_xml.findall("{DAV:}propstat"):
                status = (propstat.findtext("{DAV:}status") or "").split()
                if len(status) >= 2 and status[1] == "200":
                    ids.extend(propstat.findall("{DAV:}prop/{http://owncloud.org/ns}fileid"))
            if len(ids) != 1 or not (ids[0].text or "").isdigit() or int(ids[0].text) <= 0:
                raise ValueError("Nextcloud snapshot is missing a stable file ID")
            self.file_ids[response.path_relative_to(self.base_url).lstrip("/")] = ids[0].text
        return result


class WebDAVFilesProvider(SnapshotProvider):
    """Snapshot the full file tree of a NextCloud user via WebDAV PROPFIND.

    params:
        user (str): target NextCloud username (auth + tree owner)
        path (str, optional): relative subpath to snapshot (default "/")
        include_dirs (bool, optional): include folders to verify their creation
        include_ids (bool, optional): capture stable Nextcloud file IDs
    """

    def fetch(self, site: str, params: dict) -> Snapshot:
        user = params["user"]
        subpath = params.get("path", "/") or "/"

        base = deployed_website_urls()[site]
        root_url = f"{base}/remote.php/dav/files/{user}/"
        auth = _get_auth(site, user)

        identity_client = _IdentityClient(root_url, auth=auth) if params.get("include_ids") else None
        client_options = {"client": identity_client} if identity_client is not None else {}
        fs = WebdavFileSystem(root_url, auth=auth, **client_options)
        # fsspec otherwise silently omits directories whose listing failed.
        options = {"withdirs": True} if params.get("include_dirs") else {}
        raw = fs.find(subpath, detail=True, on_error="raise", **options)

        entries: dict[str, dict] = {}
        for path, info in raw.items():
            rel = path.lstrip("/")
            if not rel:
                continue
            etag = info.get("etag")
            if isinstance(etag, str):
                etag = etag.strip('"')
            entries[rel] = {
                "type": "dir" if info.get("type") == "directory" else "file",
                "etag": etag,
                "size": info.get("size"),
            }
            if identity_client is not None:
                if info.get("type") not in {"directory", "file"}:
                    raise ValueError("Nextcloud snapshot is missing a resource type")
                entries[rel]["file_id"] = identity_client.file_ids[rel]
        return Snapshot(entries=entries)


def _get_auth(site: str, user: str) -> tuple[str, str]:
    creds = WEBSITE_CREDENTIALS.get(site, [])
    for c in creds:
        if c["username"] == user:
            return (c["username"], c["password"])
    raise KeyError(f"No credentials for user '{user}' on site '{site}'")

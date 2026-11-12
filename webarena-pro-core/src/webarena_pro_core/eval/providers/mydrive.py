"""MyDrive file snapshots keyed by database ID, independent of names/paths."""

from __future__ import annotations

import requests

from webarena_pro_core.eval.defaults import deployed_website_url
from webarena_pro_core.eval.providers import SnapshotProvider
from webarena_pro_core.eval.snapshot import Snapshot
from webarena_pro_core.eval_token import resolve_eval_token


# The native editor uses the Google Docs MIME type; older documents can use
# application/json. Content correctness is a separate rubric, not this probe.
DOCUMENT_MIME_TYPES = {
    "application/vnd.google-apps.document",
    "application/json",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "application/pdf",
    "application/rtf",
}


class MyDriveFilesProvider(SnapshotProvider):
    """Capture every file, including other owners and trash, to detect creation.

    ``params.site`` overrides the primary task site for cross-site tasks.
    Filtering by owner, trash, or document type belongs in the final predicate;
    filtering the baseline could mistake a restore or ownership change for a
    newly created file.
    """

    def fetch(self, site: str, params: dict) -> Snapshot:
        target = params.get("site", site)
        url = f"{deployed_website_url(target).rstrip('/')}/api/eval/state"
        response = requests.get(
            url,
            headers={"X-Eval-Token": resolve_eval_token()},
            timeout=30,
            allow_redirects=False,
        )
        if response.status_code != 200:
            raise ValueError(f"MyDrive file snapshot unavailable: HTTP {response.status_code}")
        return self.from_payload(response.json())

    @staticmethod
    def from_payload(payload: object) -> Snapshot:
        """Reject stale/partial responses, even when the file collection is empty."""
        if not isinstance(payload, dict) or payload.get("fileSnapshotVersion") != 1:
            raise ValueError("MyDrive file snapshot requires fileSnapshotVersion=1; update the image")
        rows = payload.get("files")
        if not isinstance(rows, list):
            raise ValueError("MyDrive files must be an array")
        entries = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("MyDrive file must be an object")
            for key in ("id", "ownerEmail", "mimeType"):
                if not isinstance(row.get(key), str) or not row[key].strip():
                    raise ValueError(f"MyDrive file missing {key}")
            if not isinstance(row.get("inTrash"), bool):
                raise ValueError("MyDrive file inTrash must be a boolean")
            file_id = row["id"]
            if file_id in entries:
                raise ValueError("MyDrive file IDs must be unique")
            mime_type = row["mimeType"].split(";", 1)[0].strip().lower()
            entries[file_id] = {
                "owner": row["ownerEmail"],
                "inTrash": row["inTrash"],
                "document": mime_type.startswith("text/") or mime_type in DOCUMENT_MIME_TYPES,
            }
        return Snapshot(entries=entries)

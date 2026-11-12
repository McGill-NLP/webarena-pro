"""Per-site API template registry for backend_state evaluation.

Each website defines its common API patterns once. Task eval configs
reference templates by name instead of repeating URLs/headers/XML bodies.
"""

from __future__ import annotations

import copy
import re


SITE_API_REGISTRY: dict[str, dict[str, dict]] = {
    "nextcloud": {
        "calendar_events": {
            "url": "__NEXTCLOUD__/remote.php/dav/calendars/{user}/personal/",
            "method": "REPORT",
            "auth_user": "{user}",
            "headers": {"Depth": "1", "Content-Type": "application/xml"},
            "body": (
                '<?xml version="1.0"?>'
                '<c:calendar-query xmlns:c="urn:ietf:params:xml:ns:caldav" xmlns:d="DAV:">'
                "<d:prop><c:calendar-data/></d:prop>"
                '<c:filter><c:comp-filter name="VCALENDAR">'
                '<c:comp-filter name="VEVENT"/>'
                "</c:comp-filter></c:filter>"
                "</c:calendar-query>"
            ),
        },
        "file_exists": {
            "url": "__NEXTCLOUD__/remote.php/dav/files/{user}/{path}",
            "method": "GET",
            "auth_user": "{user}",
        },
        "list_directory": {
            "url": "__NEXTCLOUD__/remote.php/dav/files/{user}/{path}",
            "method": "PROPFIND",
            "auth_user": "{user}",
            "headers": {"Depth": "1"},
            "body": '<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:allprop/></d:propfind>',
        },
        "user_exists": {
            "url": "__NEXTCLOUD__/ocs/v2.php/cloud/users/{target_user}",
            "method": "GET",
            "auth_user": "admin",
            "headers": {"OCS-APIRequest": "true", "Accept": "application/json"},
        },
        "talk_rooms": {
            "url": "__NEXTCLOUD__/ocs/v2.php/apps/spreed/api/v4/room",
            "method": "GET",
            "auth_user": "{user}",
            "headers": {"OCS-APIRequest": "true", "Accept": "application/json"},
        },
        "talk_messages": {
            "url": "__NEXTCLOUD__/ocs/v2.php/apps/spreed/api/v1/chat/{token}",
            "method": "GET",
            "auth_user": "{user}",
            "headers": {"OCS-APIRequest": "true", "Accept": "application/json"},
        },
        # --- Additional templates validated against a live nextcloud ---
        "shares_list": {
            # Outgoing shares created by {user}. Each entry has share_with,
            # path, permissions (1=read, 19/31 include edit), etc.
            "url": "__NEXTCLOUD__/ocs/v2.php/apps/files_sharing/api/v1/shares",
            "method": "GET",
            "auth_user": "{user}",
            "headers": {"OCS-APIRequest": "true", "Accept": "application/json"},
        },
        "user_status": {
            # Current user's status. 404 when unset; once set, returns
            # status ("dnd"/"away"/...) and message.
            "url": "__NEXTCLOUD__/ocs/v2.php/apps/user_status/api/v1/user_status",
            "method": "GET",
            "auth_user": "{user}",
            "headers": {"OCS-APIRequest": "true", "Accept": "application/json"},
        },
        "favorite": {
            # PROPFIND a single file's oc:favorite flag (1 when favorited).
            "url": "__NEXTCLOUD__/remote.php/dav/files/{user}/{path}",
            "method": "PROPFIND",
            "auth_user": "{user}",
            "headers": {"Depth": "0", "Content-Type": "application/xml"},
            "body": (
                '<?xml version="1.0"?>'
                '<d:propfind xmlns:d="DAV:" xmlns:oc="http://owncloud.org/ns">'
                "<d:prop><oc:favorite/></d:prop></d:propfind>"
            ),
        },
        "contacts_report": {
            # Unlike PROPFIND, addressbook-query excludes the collection's
            # missing address-data property and returns complete vCards only.
            "url": "__NEXTCLOUD__/remote.php/dav/addressbooks/users/{user}/contacts/",
            "method": "REPORT",
            "auth_user": "{user}",
            "headers": {"Depth": "1", "Content-Type": "application/xml"},
            "body": (
                '<?xml version="1.0"?>'
                '<c:addressbook-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:carddav">'
                "<d:prop><c:address-data/></d:prop>"
                "</c:addressbook-query>"
            ),
        },
        "contacts": {
            # All vCards in {user}'s default address book. Names, TEL, EMAIL,
            # and CATEGORIES (contact groups) appear in the returned vCard text.
            "url": "__NEXTCLOUD__/remote.php/dav/addressbooks/users/{user}/contacts/",
            "method": "PROPFIND",
            "auth_user": "{user}",
            "headers": {"Depth": "1", "Content-Type": "application/xml"},
            "body": (
                '<?xml version="1.0"?>'
                '<d:propfind xmlns:d="DAV:" xmlns:card="urn:ietf:params:xml:ns:carddav">'
                "<d:prop><card:address-data/></d:prop></d:propfind>"
            ),
        },
    },
    # ------------------------------------------------------------------
    # mattermost — token-auth REST API (auth_mode="bearer_login").
    # Name-based endpoints resolve in a single request (great for Tier-0
    # existence checks). 404 when absent, 200 when present.
    # ------------------------------------------------------------------
    "mattermost": {
        "team_by_name": {
            "url": "__MATTERMOST__/api/v4/teams/name/{team_name}",
            "method": "GET",
            "auth_mode": "bearer_login",
            "login_url": "__MATTERMOST__/api/v4/users/login",
            "token_header": "Token",
            "auth_user": "{user}",
        },
        "channel_by_name": {
            "url": "__MATTERMOST__/api/v4/teams/name/{team_name}/channels/name/{channel_name}",
            "method": "GET",
            "auth_mode": "bearer_login",
            "login_url": "__MATTERMOST__/api/v4/users/login",
            "token_header": "Token",
            "auth_user": "{user}",
        },
        # Recent posts in a channel. Use with a `resolve` step that binds
        # {channel_id} from channel_by_name (extract "id"). The response body
        # contains all post messages, so body_contains checks message text.
        "channel_posts": {
            "url": "__MATTERMOST__/api/v4/channels/{channel_id}/posts",
            "method": "GET",
            "auth_mode": "bearer_login",
            "login_url": "__MATTERMOST__/api/v4/users/login",
            "token_header": "Token",
            "auth_user": "{user}",
        },
        # Pinned posts in a channel (same {channel_id} resolve pattern).
        "channel_pinned": {
            "url": "__MATTERMOST__/api/v4/channels/{channel_id}/pinned",
            "method": "GET",
            "auth_mode": "bearer_login",
            "login_url": "__MATTERMOST__/api/v4/users/login",
            "token_header": "Token",
            "auth_user": "{user}",
        },
        # Look up a user by username (resolve step: extract "id").
        "user_by_name": {
            "url": "__MATTERMOST__/api/v4/users/username/{username}",
            "method": "GET",
            "auth_mode": "bearer_login",
            "login_url": "__MATTERMOST__/api/v4/users/login",
            "token_header": "Token",
            "auth_user": "{user}",
        },
        # Get (or create) the DM channel between two user ids. Use as a resolve
        # step with {u1},{u2} bound from user_by_name, then extract "id" to feed
        # channel_posts. Idempotent — returns the existing DM if present.
        "dm_channel": {
            "url": "__MATTERMOST__/api/v4/channels/direct",
            "method": "POST",
            "body": "[\"{u1}\",\"{u2}\"]",
            "headers": {"Content-Type": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__MATTERMOST__/api/v4/users/login",
            "token_header": "Token",
            "auth_user": "{user}",
        },
    },
    # ------------------------------------------------------------------
    # No-API sites: the read-only `eval_state` endpoints added to each app
    # (see the websites/* changes). All are token-gated via auth_mode
    # "eval_token" (sends X-Eval-Token from WP_EVAL_TOKEN). They return the
    # app's backend state as JSON for deterministic grading.
    # ------------------------------------------------------------------
    "x-lite": {
        "eval_state": {"url": "__X-LITE__/api/eval/state", "method": "GET", "auth_mode": "eval_token"},
        # Single-table view — lets count_occurrences checks be scoped to one
        # table (e.g. bookmark deltas vs the deterministic seed baseline).
        "eval_state_table": {"url": "__X-LITE__/api/eval/state?table={table}", "method": "GET", "auth_mode": "eval_token"},
    },
    "yt-lite": {
        "eval_state": {"url": "__YT-LITE__/api/eval/state", "method": "GET", "auth_mode": "eval_token"},
    },
    "minerva-lite": {
        "eval_state": {"url": "__MINERVA-LITE__/api/eval/state", "method": "GET", "auth_mode": "eval_token"},
    },
    "jobportal": {
        "eval_state": {"url": "__JOBPORTAL__/api/eval/state", "method": "GET", "auth_mode": "eval_token"},
    },
    "acidwave": {
        "eval_state": {"url": "__ACIDWAVE__/api/eval/state", "method": "GET", "auth_mode": "eval_token"},
    },
    "mydrive": {
        "eval_state": {"url": "__MYDRIVE__/api/eval/state", "method": "GET", "auth_mode": "eval_token"},
    },
    "travelmap": {
        "eval_state": {"url": "__TRAVELMAP__/api/eval/state", "method": "GET", "auth_mode": "eval_token"},
    },
    "firefly": {
        # Standalone PHP endpoint in Firefly's public docroot; reads the
        # embedded MariaDB directly (no Laravel bootstrapping).
        "eval_state": {
            "url": "__FIREFLY__/eval_state.php",
            "method": "GET",
            "auth_mode": "eval_token",
        },
    },
    "thunderbird": {
        # Mailbox state for one user, read over local IMAP by the PHP endpoint.
        "eval_state": {
            "url": "__THUNDERBIRD__/api/eval/state.php?user={user}",
            "method": "GET",
            "auth_mode": "eval_token",
        },
    },
    'notion': {
        # Cross-workspace read-only dump (the session APIs are scoped to the
        # active workspace cookie, which verifiers cannot juggle).
        "eval_state": {"url": "__NOTION__/api/eval/state", "method": "GET", "auth_mode": "eval_token"},
    },
    'pipedrive': {
        # Read-only dump added because the clone's NextAuth session flow is
        # not verifier-drivable.
        "eval_state": {"url": "__PIPEDRIVE__/api/eval/state", "method": "GET", "auth_mode": "eval_token"},
    },
    'immich': {
        # Immich's real REST API. Login returns the token in the JSON body
        # ("accessToken"), hence login_user_key/token_json. Templates default
        # to admin@immich.local — every immich task's login_username — so the
        # verifier reads the same library the agent manipulates.
        "search_metadata": {
            # POST body comes from the task config via the {body} param, e.g.
            # '{"takenAfter": "...", "takenBefore": "...", "size": 1000}'.
            "url": "__IMMICH__/api/search/metadata",
            "method": "POST",
            "headers": {"Content-Type": "application/json", "Accept": "application/json"},
            "body": "{body}",
            "auth_mode": "bearer_login",
            "login_url": "__IMMICH__/api/auth/login",
            "login_user_key": "email",
            "token_json": "accessToken",
            "auth_user": "admin@immich.local",
        },
        "albums": {
            "url": "__IMMICH__/api/albums",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__IMMICH__/api/auth/login",
            "login_user_key": "email",
            "token_json": "accessToken",
            "auth_user": "admin@immich.local",
        },
        "album_info": {
            "url": "__IMMICH__/api/albums/{album_id}",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__IMMICH__/api/auth/login",
            "login_user_key": "email",
            "token_json": "accessToken",
            "auth_user": "admin@immich.local",
        },
        "asset_info": {
            "url": "__IMMICH__/api/assets/{asset_id}",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__IMMICH__/api/auth/login",
            "login_user_key": "email",
            "token_json": "accessToken",
            "auth_user": "admin@immich.local",
        },
        "people": {
            "url": "__IMMICH__/api/people",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__IMMICH__/api/auth/login",
            "login_user_key": "email",
            "token_json": "accessToken",
            "auth_user": "admin@immich.local",
        },
        "admin_users": {
            "url": "__IMMICH__/api/admin/users",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__IMMICH__/api/auth/login",
            "login_user_key": "email",
            "token_json": "accessToken",
            "auth_user": "admin@immich.local",
        },
        "server_statistics": {
            "url": "__IMMICH__/api/server/statistics",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__IMMICH__/api/auth/login",
            "login_user_key": "email",
            "token_json": "accessToken",
            "auth_user": "admin@immich.local",
        },
        "faces": {
            "url": "__IMMICH__/api/faces?id={asset_id}",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__IMMICH__/api/auth/login",
            "login_user_key": "email",
            "token_json": "accessToken",
            "auth_user": "admin@immich.local",
        },
        # Elevates the evaluator's session so locked-folder assets become
        # readable (and doubles as a Tier-0 check that the PIN equals {pin}).
        # Use as a `resolve` step before a visibility=locked search.
        "session_unlock": {
            "url": "__IMMICH__/api/auth/session/unlock",
            "method": "POST",
            "headers": {"Content-Type": "application/json", "Accept": "application/json"},
            "body": "{\"pinCode\": \"{pin}\"}",
            "auth_mode": "bearer_login",
            "login_url": "__IMMICH__/api/auth/login",
            "login_user_key": "email",
            "token_json": "accessToken",
            "auth_user": "admin@immich.local",
        },
        "auth_status": {
            "url": "__IMMICH__/api/auth/status",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__IMMICH__/api/auth/login",
            "login_user_key": "email",
            "token_json": "accessToken",
            "auth_user": "admin@immich.local",
        },
    },
    'metabase': {
        "cards": {
            "url": "__METABASE__/api/card",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__METABASE__/api/session",
            "login_user_key": "username",
            "token_json": "id",
            "auth_header": "X-Metabase-Session",
            "auth_user": "admin@admin.com",
        },
        "dashboard": {
            "url": "__METABASE__/api/dashboard/{dashboard_id}",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__METABASE__/api/session",
            "login_user_key": "username",
            "token_json": "id",
            "auth_header": "X-Metabase-Session",
            "auth_user": "admin@admin.com",
        },
        "dashboards": {
            "url": "__METABASE__/api/dashboard",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__METABASE__/api/session",
            "login_user_key": "username",
            "token_json": "id",
            "auth_header": "X-Metabase-Session",
            "auth_user": "admin@admin.com",
        },
        "setting": {
            "url": "__METABASE__/api/setting/{setting_key}",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__METABASE__/api/session",
            "login_user_key": "username",
            "token_json": "id",
            "auth_header": "X-Metabase-Session",
            "auth_user": "admin@admin.com",
        },
    },
    'flight-search': {
        "eval_state": {
            "url": "__FLIGHT-SEARCH__/api/eval/state", "method": "GET", "auth_mode": "eval_token",
        },
        "search": {
            "url": "__FLIGHT-SEARCH__/api/search",
            "method": "POST",
            "headers": {"Content-Type": "application/json", "Accept": "application/json"},
            "body": "{body}",
            "auth_mode": "bearer_login",
            "login_url": "__FLIGHT-SEARCH__/api/auth/verify",
            "login_user_key": "passkey",
            "token_cookie": "flight_auth",
            "auth_user": "flyingagents",
        },
        "bookings": {
            "url": "__FLIGHT-SEARCH__/api/bookings",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__FLIGHT-SEARCH__/api/auth/verify",
            "login_user_key": "passkey",
            "token_cookie": "flight_auth",
            "auth_user": "flyingagents",
        },
    },
    'erp-next': {
        "resource": {
            "url": "__ERP-NEXT__/api/resource/{doctype}?{query}",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__ERP-NEXT__/api/method/login",
            "login_user_key": "usr",
            "login_password_key": "pwd",
            "token_cookie": "sid",
            "auth_user": "Administrator",
        },
    },
    'peppermint': {
        "tickets_all": {
            "url": "__PEPPERMINT__/api/v1/tickets/all",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__PEPPERMINT__/api/v1/auth/login",
            "login_user_key": "email",
            "token_json": "token",
            "auth_user": "admin@admin.com",
        },
        "ticket": {
            "url": "__PEPPERMINT__/api/v1/ticket/{ticket_id}",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "auth_mode": "bearer_login",
            "login_url": "__PEPPERMINT__/api/v1/auth/login",
            "login_user_key": "email",
            "token_json": "token",
            "auth_user": "admin@admin.com",
        },
    },
    'penpot': {
        "rpc": {
            "url": "__PENPOT__/api/rpc/command/{command}",
            "method": "POST",
            "headers": {"Content-Type": "application/json", "Accept": "application/json"},
            "body": "{body}",
            "auth_mode": "bearer_login",
            "login_url": "__PENPOT__/api/rpc/command/login-with-password",
            "login_user_key": "email",
            "token_cookie": "auth-token",
            "auth_user": "admin@penpot.local",
        },
    },
}

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def get_api_template(site: str, api_name: str) -> dict:
    """Look up an API template by site and name. Returns a deep copy."""
    site_apis = SITE_API_REGISTRY.get(site)
    if site_apis is None:
        raise KeyError(f"No API registry for site '{site}'")
    template = site_apis.get(api_name)
    if template is None:
        raise KeyError(
            f"No API template '{api_name}' for site '{site}'. "
            f"Available: {list(site_apis.keys())}"
        )
    return copy.deepcopy(template)


def _fill_placeholders(value: str, params: dict[str, str]) -> str:
    """Replace {key} placeholders in a string with values from params.

    Runs to a fixpoint (bounded) so params whose values themselves contain
    placeholders resolve too — e.g. penpot's generic rpc template, where the
    {body} param is a JSON string that references a resolve-bound {file_id}.
    Unknown placeholders are left as-is and cannot loop.
    """

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        if key in params:
            return str(params[key])
        return match.group(0)  # leave unresolved placeholders as-is

    for _ in range(5):
        filled = _PLACEHOLDER_RE.sub(_replace, value)
        if filled == value:
            break
        value = filled
    return value


def resolve_api_template(site: str, api_name: str, params: dict[str, str] | None = None) -> dict:
    """Look up template and fill {param} placeholders from params dict.

    Returns a dict with keys like ``url``, ``method``, ``auth_user``,
    ``headers``, ``body`` — ready to be consumed by ``BackendStateEvaluator``.
    """
    template = get_api_template(site, api_name)
    if not params:
        return template

    resolved: dict = {}
    for key, value in template.items():
        if isinstance(value, str):
            resolved[key] = _fill_placeholders(value, params)
        elif isinstance(value, dict):
            resolved[key] = {
                k: _fill_placeholders(v, params) if isinstance(v, str) else v
                for k, v in value.items()
            }
        else:
            resolved[key] = value
    return resolved

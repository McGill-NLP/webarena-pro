"""Shared HTTP helpers for Metabase snapshot providers.

Metabase auth works by POSTing to ``/api/session`` with admin credentials
and getting back an opaque session id that's then sent as
``X-Metabase-Session`` on every subsequent API request. Session ids are
cached per ``site`` in-process so the three providers don't re-login on
every fetch.
"""

from __future__ import annotations

import requests

from webarena_pro_core.eval.defaults import (
    DEPLOYED_WEBSITE_URLS,
    WEBSITE_CREDENTIALS,
)

_SESSION_CACHE: dict[str, str] = {}


def _admin_creds(site: str) -> tuple[str, str]:
    creds = WEBSITE_CREDENTIALS.get(site) or []
    if not creds:
        raise KeyError(f"No credentials configured for site '{site}'")
    c = creds[0]
    return c["username"], c["password"]


def _login(site: str) -> str:
    base = DEPLOYED_WEBSITE_URLS[site]
    username, password = _admin_creds(site)
    resp = requests.post(
        f"{base}/api/session",
        json={"username": username, "password": password},
        timeout=30,
    )
    resp.raise_for_status()
    token = resp.json().get("id")
    if not token:
        raise RuntimeError("Metabase /api/session returned no session id")
    return token


def session_token(site: str) -> str:
    """Return a cached session id, logging in on first use."""
    token = _SESSION_CACHE.get(site)
    if token:
        return token
    token = _login(site)
    _SESSION_CACHE[site] = token
    return token


def _request(site: str, method: str, path: str, **kwargs) -> requests.Response:
    base = DEPLOYED_WEBSITE_URLS[site]
    token = session_token(site)
    headers = kwargs.pop("headers", {}) or {}
    headers.setdefault("X-Metabase-Session", token)
    headers.setdefault("Accept", "application/json")
    resp = requests.request(
        method, f"{base}{path}", headers=headers, timeout=30, **kwargs
    )
    # If the cached token was rejected (401), retry once with a fresh login.
    if resp.status_code == 401:
        _SESSION_CACHE.pop(site, None)
        headers["X-Metabase-Session"] = session_token(site)
        resp = requests.request(
            method, f"{base}{path}", headers=headers, timeout=30, **kwargs
        )
    return resp


def api_get(site: str, path: str, params: dict | None = None) -> list | dict:
    resp = _request(site, "GET", path, params=params)
    resp.raise_for_status()
    return resp.json()

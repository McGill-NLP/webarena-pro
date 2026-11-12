"""Deployment URLs and login routes shared by task setup and evaluation."""

from __future__ import annotations

import os
from typing import Sequence

from . import WEBSITES_FIXED_URLS, site_env_var_key

WEBSITE_LOGIN_PATHS = {
    "password-manager": "",
    "nextcloud": "/login",
    "flight-search": "",
    "thunderbird": "",
    "jobportal": "/accounts/login/",
    "travelmap": "/login",
    "mattermost": "/login",
    "firefly": "/login",
    "immich": "/auth/login",
    "metabase": "/auth/login",
    "mydrive": "",
    "notion": "/login",
    "acidwave": "",
    "minerva-lite": "/login",
    "yt-lite": "/login",
    "x-lite": "/login",
    "peppermint": "/auth/login",
    "penpot": "",
    "pipedrive": "/login",
    "erp-next": "/login",
}


def _url_env_var(site: str) -> str:
    return f"WP_{site_env_var_key(site)}_URL"


def deployed_website_url(site: str) -> str:
    return os.getenv(_url_env_var(site), WEBSITES_FIXED_URLS[site])


def deployed_website_urls(sites: Sequence[str] | None = None) -> dict[str, str]:
    site_names = WEBSITES_FIXED_URLS if sites is None else sites
    return {site: deployed_website_url(site) for site in site_names}


def deployed_website_login_url(site: str) -> str | None:
    login_path = WEBSITE_LOGIN_PATHS.get(site)
    if login_path is None:
        return None
    return f"{deployed_website_url(site)}{login_path}"


def deployed_website_login_urls(sites: Sequence[str] | None = None) -> dict[str, str]:
    site_names = WEBSITE_LOGIN_PATHS if sites is None else sites
    login_urls: dict[str, str] = {}
    for site in site_names:
        login_url = deployed_website_login_url(site)
        if login_url is not None:
            login_urls[site] = login_url
    return login_urls

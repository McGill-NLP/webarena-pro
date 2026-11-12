"""Shared site configuration, credential resolution, and login predicates."""

from __future__ import annotations

import logging
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import urlparse

from webarena_pro_core.config import WEBSITE_CREDENTIALS
from webarena_pro_core.website_metadata import (
    deployed_website_urls,
    deployed_website_login_urls,
)

logger = logging.getLogger(__name__)

LOGIN_MAX_ATTEMPTS = 3
LOGIN_RETRY_DELAY_SECONDS = 2.0
LOGIN_VERIFY_TIMEOUT_MS = 15000
PENPOT_LOGIN_FORM_TIMEOUT_MS = 60000

Credential = Mapping[str, str]
CredentialStore = Mapping[str, Sequence[Credential]]
ReadyCallback = Callable[[str], None]

def _credential_identifier(credential: Credential, *, site: str) -> str:
    # MyDrive authenticates by email; its username is used for file sharing.
    if site == "mydrive" and credential.get("email"):
        return str(credential["email"])
    if "username" in credential:
        return str(credential["username"])
    if "email" in credential:
        return str(credential["email"])
    raise RuntimeError(
        f"Credential entry for site '{site}' must include either 'username' or 'email'."
    )


def _normalize_url_path(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path or "/"
    return path.rstrip("/") or "/"


def _mattermost_login_finished(url: Any) -> bool:
    path = getattr(url, "path", None)
    if not isinstance(path, str):
        path = _normalize_url_path(str(url))
    path = path.rstrip("/") or "/"
    return not path.startswith(("/login", "/landing"))


class AutoLoginConfig:
    def __init__(
        self,
        *,
        urls: Mapping[str, str] | None = None,
        login_urls: Mapping[str, str] | None = None,
        credentials: CredentialStore | None = None,
        wait_until_ready: ReadyCallback | None = None,
    ) -> None:
        self.urls = dict(urls or deployed_website_urls())
        self.login_urls = dict(login_urls or deployed_website_login_urls())
        self.credentials = {
            site: [dict(credential) for credential in site_credentials]
            for site, site_credentials in (credentials or WEBSITE_CREDENTIALS).items()
        }
        self.wait_until_ready = wait_until_ready

    def resolve_credentials(
        self,
        site: str,
        username: str | None = None,
    ) -> tuple[str, str]:
        site_credentials = self.credentials.get(site)
        if not site_credentials:
            raise RuntimeError(f"No credentials configured for site '{site}'.")

        if username is not None:
            for credential in site_credentials:
                if username and username in (
                    credential.get("username"),
                    credential.get("email"),
                ):
                    return _credential_identifier(credential, site=site), str(
                        credential["password"]
                    )
            raise RuntimeError(
                f"No credentials found for username '{username}' on site '{site}'."
            )

        credential = site_credentials[0]
        return _credential_identifier(credential, site=site), str(credential["password"])

    def resolve_passkey(self, site: str) -> str:
        site_credentials = self.credentials.get(site)
        if not site_credentials:
            raise RuntimeError(f"No credentials configured for site '{site}'.")

        passkey = site_credentials[0].get("passkey")
        if passkey is None:
            raise RuntimeError(f"No passkey configured for site '{site}'.")
        return str(passkey)

    def resolve_jobportal_user_type(self, username: str) -> str:
        for credential in self.credentials.get("jobportal", []):
            candidate = credential.get("username") or credential.get("email")
            if candidate == username:
                user_type = credential.get("user_type")
                if user_type in {"employer", "job_seeker"}:
                    return str(user_type)

        if username == "alice_seeker":
            return "job_seeker"
        return "employer"



async def run_ready_callback(callback, site: str) -> None:
    """Allow async readiness hooks; run legacy blocking hooks off the event loop."""
    import asyncio
    import inspect

    if inspect.iscoroutinefunction(callback):
        await callback(site)
    else:
        result = await asyncio.to_thread(callback, site)
        if inspect.isawaitable(result):
            await result


async def async_any(values) -> bool:
    """Preserve any()'s short circuit when a browser probe is awaitable."""
    try:
        async for value in values:
            if value:
                return True
        return False
    finally:
        await values.aclose()

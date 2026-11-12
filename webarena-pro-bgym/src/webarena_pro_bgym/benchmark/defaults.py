"""Compatibility exports for WebArena-Pro benchmark defaults."""

from webarena_pro_core.website_metadata import (
    WEBSITE_LOGIN_PATHS as _WEBSITE_LOGIN_PATHS,
    deployed_website_login_url,
    deployed_website_login_urls,
    deployed_website_url,
    deployed_website_urls,
)
from webarena_pro_core.config import WEBSITE_CREDENTIALS
from webarena_pro_core.task import DEPLOYED_WEBSITE_LOGIN_URLS, DEPLOYED_WEBSITE_URLS

__all__ = [
    "DEPLOYED_WEBSITE_LOGIN_URLS",
    "DEPLOYED_WEBSITE_URLS",
    "WEBSITE_CREDENTIALS",
    "_WEBSITE_LOGIN_PATHS",
    "deployed_website_login_url",
    "deployed_website_login_urls",
    "deployed_website_url",
    "deployed_website_urls",
]

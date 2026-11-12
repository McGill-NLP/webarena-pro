"""BrowserGym-specific reset and container ownership policy."""

from __future__ import annotations

import os

from webarena_pro_core import state_reset as core_reset


def reset_enabled() -> bool:
    """Return whether BrowserGym should reset sites before every task."""
    raw = os.environ.get("WP_RESET_CONTAINER_PER_TASK")
    if raw is None:
        return True
    return raw.lower() not in {"0", "false", "no"}


def reset_site(site: str) -> None:
    """Reset one selected site through the core reset API."""
    core_reset.reset_site(site)


def stop_site(site: str) -> None:
    """Stop a task-owned container when using the container backend."""
    if core_reset.reset_backend_for_site(site) == core_reset.CONTAINER_BACKEND:
        core_reset.stop_site_container(site)

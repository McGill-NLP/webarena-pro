"""Snapshot providers: per-resource fetchers that return a ``Snapshot``.

Each provider knows how to talk to one kind of backend resource
(WebDAV files, CalDAV events, Talk rooms, OCS users, ...) and produces a
generic ``Snapshot`` that can then be diffed uniformly.

Registration happens at import time via ``register_provider()``. Tasks
reference providers by name in their eval config::

    {"baseline": [
        {"name": "files", "provider": "webdav_files", "params": {"user": "maya.patel"}}
    ]}
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from webarena_pro_core.eval.snapshot import Snapshot


class SnapshotProvider(ABC):
    """Fetch a ``Snapshot`` from a live backend."""

    @abstractmethod
    def fetch(self, site: str, params: dict) -> Snapshot:
        """Fetch current state, raising if the request or response is invalid.

        Empty entries must mean a successfully observed empty collection,
        never a failed fetch or a partially retrieved collection.
        """


_REGISTRY: dict[str, SnapshotProvider] = {}


def register_provider(name: str, provider: SnapshotProvider) -> None:
    _REGISTRY[name] = provider


def get_provider(name: str) -> SnapshotProvider:
    if name not in _REGISTRY:
        raise KeyError(
            f"No snapshot provider registered for '{name}'. "
            f"Available: {list(_REGISTRY.keys())}"
        )
    return _REGISTRY[name]


def available_providers() -> list[str]:
    return sorted(_REGISTRY.keys())


# ---------------------------------------------------------------------------
# Auto-register built-in providers at import time
# ---------------------------------------------------------------------------

def _register_builtins() -> None:
    from webarena_pro_core.eval.providers.immich_assets import ImmichAssetsProvider
    from webarena_pro_core.eval.providers.webdav import WebDAVFilesProvider
    from webarena_pro_core.eval.providers.caldav import CalDAVEventsProvider
    from webarena_pro_core.eval.providers.talk import TalkRoomsProvider
    from webarena_pro_core.eval.providers.ocs_users import OCSUsersProvider
    from webarena_pro_core.eval.providers.carddav import CardDAVContactsProvider
    from webarena_pro_core.eval.providers.activity import ActivityLogProvider
    from webarena_pro_core.eval.providers.metabase_cards import MetabaseCardsProvider
    from webarena_pro_core.eval.providers.mydrive import MyDriveFilesProvider
    from webarena_pro_core.eval.providers.metabase_dashboards import (
        MetabaseDashboardsProvider,
    )
    from webarena_pro_core.eval.providers.metabase_timeline_events import (
        MetabaseTimelineEventsProvider,
    )

    register_provider("immich_assets", ImmichAssetsProvider())
    register_provider("webdav_files", WebDAVFilesProvider())
    register_provider("caldav_events", CalDAVEventsProvider())
    register_provider("talk_rooms", TalkRoomsProvider())
    register_provider("ocs_users", OCSUsersProvider())
    register_provider("carddav_contacts", CardDAVContactsProvider())
    register_provider("activity_log", ActivityLogProvider())
    register_provider("metabase_cards", MetabaseCardsProvider())
    register_provider("mydrive_files", MyDriveFilesProvider())
    register_provider("metabase_dashboards", MetabaseDashboardsProvider())
    register_provider("metabase_timeline_events", MetabaseTimelineEventsProvider())


_register_builtins()

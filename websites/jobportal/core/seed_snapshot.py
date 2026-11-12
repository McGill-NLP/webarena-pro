"""SQLite snapshots for deterministic, fast episode reset."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3

from django.conf import settings
from django.db import connections


def snapshot_paths():
    config = settings.DATABASES["default"]
    if config["ENGINE"] != "django.db.backends.sqlite3" or str(config["NAME"]) == ":memory:":
        return None
    return (
        Path(config["NAME"]),
        Path(os.getenv("JOBPORTAL_SEED_SNAPSHOT", "/opt/webarena-seed/jobportal.sqlite3")),
    )


def create_seed_snapshot():
    paths = snapshot_paths()
    if paths is None:
        raise RuntimeError("Seed snapshots require a file-backed SQLite database")
    database, snapshot = paths
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    connections.close_all()
    temporary = snapshot.with_suffix(".tmp")
    with closing(sqlite3.connect(database)) as source:
        with closing(sqlite3.connect(temporary)) as target:
            source.backup(target)
    temporary.replace(snapshot)


def restore_seed_snapshot():
    paths = snapshot_paths()
    if paths is None:
        return False
    database, snapshot = paths
    if not snapshot.is_file():
        return False
    database.parent.mkdir(parents=True, exist_ok=True)
    connections.close_all()
    with closing(sqlite3.connect(snapshot.resolve().as_uri() + "?mode=ro", uri=True)) as source:
        with closing(sqlite3.connect(database, timeout=60)) as target:
            source.backup(target)
    return True

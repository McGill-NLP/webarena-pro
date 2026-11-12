#!/usr/bin/env python3
"""Initialize Roundcube's SQLite database and the primary user's contacts."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path


ASSET_DIR = Path(os.environ.get("SEED_ASSET_DIR", "/opt/thunderbird-seed/seed_assets"))
DATABASE = Path(os.environ.get("ROUNDCUBE_DB", "/var/lib/roundcube/roundcube.db"))
SCHEMA = Path(os.environ.get("ROUNDCUBE_SCHEMA", "/var/www/roundcube/SQL/sqlite.initial.sql"))
MAIL_HOST = "127.0.0.1"
CHANGED = "2026-07-10 17:00:00"


def vcard_escape(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def vcard(contact: dict[str, str]) -> str:
    return "\r\n".join(
        [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"FN:{vcard_escape(contact['name'])}",
            f"N:{vcard_escape(contact['surname'])};{vcard_escape(contact['firstname'])};;;",
            f"EMAIL;TYPE=INTERNET:{contact['email']}",
            "REV:2026-07-10T17:00:00Z",
            "END:VCARD",
            "",
        ]
    )


def main() -> int:
    manifest = json.loads((ASSET_DIR / "manifest.json").read_text(encoding="utf-8"))
    contacts = json.loads((ASSET_DIR / "contacts.json").read_text(encoding="utf-8"))
    if len(contacts) != manifest["contact_count"]:
        raise RuntimeError("Contact count does not match seed manifest")

    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    DATABASE.unlink(missing_ok=True)
    connection = sqlite3.connect(DATABASE)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(SCHEMA.read_text(encoding="utf-8"))

    user_ids: dict[str, int] = {}
    for user in manifest["users"]:
        cursor = connection.execute(
            "INSERT INTO users (username, mail_host, created, language, preferences) VALUES (?, ?, ?, ?, ?)",
            (user["email"], MAIL_HOST, CHANGED, "en_US", "a:0:{}"),
        )
        user_id = int(cursor.lastrowid)
        user_ids[user["email"]] = user_id
        connection.execute(
            """
            INSERT INTO identities
                (user_id, changed, del, standard, name, organization, email, "reply-to", bcc, signature, html_signature)
            VALUES (?, ?, 0, 1, ?, 'TechCorp', ?, '', '', '', 0)
            """,
            (user_id, CHANGED, user["name"], user["email"]),
        )

    primary_user_id = user_ids[manifest["primary_user"]]
    group_cursor = connection.execute(
        "INSERT INTO contactgroups (user_id, changed, del, name) VALUES (?, ?, 0, ?)",
        (primary_user_id, CHANGED, "TechCorp Directory"),
    )
    group_id = int(group_cursor.lastrowid)

    for contact in contacts:
        words = " ".join(
            [
                contact["name"].casefold(),
                contact["firstname"].casefold(),
                contact["surname"].casefold(),
                contact["email"].casefold(),
            ]
        )
        cursor = connection.execute(
            """
            INSERT INTO contacts
                (user_id, changed, del, name, email, firstname, surname, vcard, words)
            VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?)
            """,
            (
                primary_user_id,
                CHANGED,
                contact["name"],
                contact["email"],
                contact["firstname"],
                contact["surname"],
                vcard(contact),
                words,
            ),
        )
        connection.execute(
            "INSERT INTO contactgroupmembers (contactgroup_id, contact_id, created) VALUES (?, ?, ?)",
            (group_id, int(cursor.lastrowid), CHANGED),
        )

    connection.commit()
    connection.close()
    print(f"Seeded Roundcube users={len(user_ids)} contacts={len(contacts)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Audit Thunderbird seed integrity and benchmark-task feasibility.

This is intentionally read-only. It validates the generated corpus/address book,
the original task fixtures, and every benchmark task that uses Thunderbird.
"""

from __future__ import annotations

import gzip
import json
import re
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[3]
THUNDERBIRD_ROOT = REPO_ROOT / "websites" / "thunderbird"
CONFIG_ROOT = REPO_ROOT / "webarena-pro" / "src" / "webarena_pro"
PRIMARY_USER = "alice@techcorp.local"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def main() -> int:
    failures: list[str] = []

    def check(condition: bool, message: str) -> None:
        if not condition:
            failures.append(message)

    manifest = load_json(THUNDERBIRD_ROOT / "seed_assets" / "manifest.json")
    contacts = load_json(THUNDERBIRD_ROOT / "seed_assets" / "contacts.json")
    fixtures = load_json(THUNDERBIRD_ROOT / "seed_data.json")
    contact_emails = [contact["email"].casefold() for contact in contacts]
    contact_by_email = {contact["email"].casefold(): contact for contact in contacts}
    user_emails = {user["email"].casefold() for user in manifest["users"]}

    check(len(contacts) == manifest["contact_count"], "manifest contact_count is stale")
    check(len(contact_emails) == len(set(contact_emails)), "address book contains duplicate email addresses")
    check(
        len({contact["name"].casefold() for contact in contacts}) == len(contacts),
        "address book contains duplicate display names",
    )
    check(
        not any(re.search(r"\s\d+$", contact["surname"]) for contact in contacts),
        "address book contains numeric surname suffixes",
    )
    check(
        all(
            contact["email"].casefold().startswith(
                f"{contact['firstname']}.{contact['surname']}.".casefold()
            )
            for contact in contacts
        ),
        "a contact name is inconsistent with its generated email address",
    )
    check(len(manifest["users"]) == 4, "the four original Thunderbird accounts were not preserved")
    check(
        user_emails
        == {
            "alice@techcorp.local",
            "bob@techcorp.local",
            "carol@techcorp.local",
            "david@techcorp.local",
        },
        "the original Thunderbird account set changed",
    )
    check(
        not ({"bob@techcorp.local", "carol@techcorp.local"} & set(contact_emails)),
        "Bob or Carol is pre-seeded, which makes the add-contact tasks ambiguous",
    )

    corpus_messages: list[dict[str, Any]] = []
    corpus_participants: set[str] = set()
    participant_name_mismatches: list[tuple[str, str]] = []
    with gzip.open(THUNDERBIRD_ROOT / "seed_assets" / "messages.jsonl.gz", "rt", encoding="utf-8") as handle:
        for line in handle:
            message = json.loads(line)
            corpus_messages.append(message)
            for field in ("from", "to", "cc", "bcc"):
                people = message.get(field, [])
                if isinstance(people, dict):
                    people = [people]
                for person in people:
                    if isinstance(person, dict) and person.get("email"):
                        email = person["email"].casefold()
                        corpus_participants.add(email)
                        contact = contact_by_email.get(email)
                        if contact is not None and person.get("name") != contact["name"]:
                            participant_name_mismatches.append((person.get("name", ""), email))

    corpus_participants.discard(PRIMARY_USER)
    check(
        len(corpus_messages) == manifest["corpus_message_count"] == 5000,
        "corpus must contain exactly 5,000 generated messages",
    )
    missing_contacts = corpus_participants - set(contact_emails)
    check(not missing_contacts, f"corpus participants missing from contacts: {sorted(missing_contacts)[:5]}")
    check(
        not participant_name_mismatches,
        f"corpus participant names differ from contacts: {participant_name_mismatches[:5]}",
    )
    check(
        all(email.endswith("@techcorp.local") for email in contact_emails),
        "an address-book entry escaped anonymization",
    )

    latest_corpus = max(corpus_messages, key=lambda message: parse_timestamp(message["date"]))
    latest_alice_fixture = max(
        (
            message
            for message in fixtures["emails"]
            if PRIMARY_USER in message.get("delivery", {})
        ),
        key=lambda message: parse_timestamp(message["date"]),
    )
    check(
        latest_alice_fixture["from"] == "david@techcorp.local"
        and parse_timestamp(latest_alice_fixture["date"])
        > parse_timestamp(latest_corpus["date"]),
        "the unchanged most-recent-correspondent tasks no longer resolve to David",
    )

    deliveries: dict[str, dict[str, list[tuple[dict[str, Any], set[str]]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for message in fixtures["emails"]:
        for user, delivery in message["delivery"].items():
            deliveries[user][delivery["folder"]].append((message, set(delivery["flags"])))

    alice_trash_unread = {
        message["subject"]
        for message, flags in deliveries[PRIMARY_USER]["Trash"]
        if "\\Seen" not in flags
    }
    check(
        alice_trash_unread == {"TechCrunch Daily: AI dominates Q1 fundraising"},
        "Alice's unread-trash task fixture is missing or no longer unique",
    )

    carol_inbox = deliveries["carol@techcorp.local"]["INBOX"]
    carol_senders = defaultdict(int)
    for message, _flags in carol_inbox:
        carol_senders[message["from"]] += 1
    check(
        dict(carol_senders)
        == {
            "bob@techcorp.local": 2,
            "alice@techcorp.local": 2,
            "david@techcorp.local": 2,
        },
        "Carol's move/flag task no longer has exactly two messages per required sender",
    )

    bob_inbox = deliveries["bob@techcorp.local"]["INBOX"]
    bob_unread = {message["subject"] for message, flags in bob_inbox if "\\Seen" not in flags}
    bob_recent_read = {
        message["subject"]
        for message, flags in bob_inbox
        if "\\Seen" in flags and datetime.fromisoformat(message["date"]).date() > date(2026, 2, 20)
    }
    check(bob_unread == {"Team Lunch Friday? 🍕"}, "Bob's unread-vacation task fixture changed")
    check(
        bob_recent_read
        == {"Sprint Planning Notes - Sprint 14", "Security Review: New Auth Endpoints"},
        "Bob's post-February-20 vacation task fixtures changed",
    )

    david_inbox = deliveries["david@techcorp.local"]["INBOX"]
    david_unread = {message["subject"] for message, flags in david_inbox if "\\Seen" not in flags}
    david_read_after_jan_15 = {
        message["subject"]
        for message, flags in david_inbox
        if "\\Seen" in flags and datetime.fromisoformat(message["date"]).date() > date(2026, 1, 15)
    }
    david_read_after_jan_20 = {
        message["subject"]
        for message, flags in david_inbox
        if "\\Seen" in flags and datetime.fromisoformat(message["date"]).date() > date(2026, 1, 20)
    }
    check(
        david_unread
        == {
            "Sprint Review Tomorrow - 2pm",
            "Team Lunch Friday? 🍕",
            "UI Testing Request: Dashboard Redesign",
        },
        "David's unread-vacation task fixtures changed",
    )
    check(
        david_read_after_jan_15
        == {
            "Re: Q1 2026 Planning Meeting - Action Items",
            "Re: Critical Bug: Payment Processing Failure on Checkout",
        },
        "David's post-January-15 task fixtures changed",
    )
    check(
        david_read_after_jan_20 == {"Re: Critical Bug: Payment Processing Failure on Checkout"},
        "David's post-January-20 task fixture changed",
    )

    lunch = next(message for message in fixtures["emails"] if message["id"] == "msg-016")
    check("Pizza" in lunch["body"], "the Penpot task does not expose its expected team name")
    check(
        set(lunch["to"])
        == {
            "alice@techcorp.local",
            "bob@techcorp.local",
            "david@techcorp.local",
        }
        and lunch["from"] == "carol@techcorp.local",
        "the Team Lunch participant list no longer matches the Penpot rubric",
    )

    semantic_fields = ("intent", "sites", "login_username", "login_usernames", "start_url", "eval")
    thunderbird_tasks: list[dict[str, Any]] = []
    for anonymous_path in sorted((CONFIG_ROOT / "anonymous_configs").glob("*.raw.json")):
        regular_path = CONFIG_ROOT / "config" / anonymous_path.name
        if not regular_path.exists():
            continue
        anonymous = {task["task_id"]: task for task in load_json(anonymous_path)}
        regular = {task["task_id"]: task for task in load_json(regular_path)}
        for task_id, task in anonymous.items():
            if "thunderbird" not in task.get("sites", []):
                continue
            thunderbird_tasks.append(task)
            check(task_id in regular, f"{anonymous_path.name}:{task_id} missing from regular config")
            if task_id in regular:
                for field in semantic_fields:
                    check(
                        task.get(field) == regular[task_id].get(field),
                        f"{anonymous_path.name}:{task_id} differs between config copies in {field}",
                    )
            check(bool(task.get("intent", "").strip()), f"{task_id} has an empty intent")
            rubrics = task.get("eval", {}).get("rubrics", [])
            check(bool(rubrics), f"{task_id} has no rubrics")
            check(
                all(rubric.get("type") in {"action", "outcome"} and rubric.get("text", "").strip() for rubric in rubrics),
                f"{task_id} has an invalid rubric",
            )
            mail_login = task.get("login_usernames", {}).get("thunderbird")
            check(mail_login in user_emails, f"{task_id} uses unknown Thunderbird login {mail_login!r}")

    check(len(thunderbird_tasks) == 24, "expected 24 tasks that depend on Thunderbird")
    native_tasks = {
        task["task_id"]: task
        for task in thunderbird_tasks
        if task.get("sites") == ["thunderbird"]
        or task["task_id"] == "20260505055330982132"
    }
    check(len(native_tasks) == 12, "expected 12 Thunderbird task records")

    if failures:
        print("Thunderbird task audit FAILED")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("Thunderbird task audit passed")
    print(f"- original accounts: {len(manifest['users'])}")
    print(f"- generated contacts: {len(contacts)}")
    print(f"- corpus messages: {len(corpus_messages)}")
    print(f"- native task records: {len(native_tasks)}")
    print(f"- all tasks using Thunderbird: {len(thunderbird_tasks)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

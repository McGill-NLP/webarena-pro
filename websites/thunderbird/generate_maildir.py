#!/usr/bin/env python3
"""Generate Maildir state from task fixtures and the anonymized Enron sample."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.utils import format_datetime
from pathlib import Path


HERE = Path(__file__).resolve().parent
MAILDIR_BASE = Path(os.environ.get("MAILDIR_BASE", "/var/vmail"))
SEED_FILE = HERE / "seed_data.json"
ASSET_DIR = Path(os.environ.get("SEED_ASSET_DIR", HERE / "seed_assets"))
MANIFEST_FILE = ASSET_DIR / "manifest.json"
MESSAGES_FILE = ASSET_DIR / "messages.jsonl.gz"
STANDARD_FOLDERS = {"Sent", "Trash", "Drafts"}


def maildir_name(user_email: str) -> Path:
    local, domain = user_email.split("@", 1)
    return MAILDIR_BASE / domain / local


def ensure_maildir(base_path: Path, folder: str | None = None) -> Path:
    path = base_path / "Maildir"
    if folder and folder.upper() != "INBOX":
        path /= f".{folder}"
    for subdirectory in ("cur", "new", "tmp"):
        (path / subdirectory).mkdir(parents=True, exist_ok=True)
    return path


def unique_filename(date: datetime, index: int) -> str:
    token = hashlib.sha1(f"{date.isoformat()}:{index}".encode()).hexdigest()[:12]
    return f"{int(date.timestamp())}.M{token}P{index:05d}.techcorp.local"


def write_maildir_message(
    folder_path: Path,
    message: bytes,
    flags: list[str],
    date: datetime,
    index: int,
) -> None:
    flag_chars = []
    if "\\Answered" in flags:
        flag_chars.append("R")
    if "\\Seen" in flags:
        flag_chars.append("S")
    if "\\Flagged" in flags:
        flag_chars.append("F")
    if "\\Deleted" in flags:
        flag_chars.append("T")

    base_name = unique_filename(date, index)
    if "\\Seen" in flags:
        output = folder_path / "cur" / f"{base_name}:2,{''.join(sorted(flag_chars))}"
    else:
        output = folder_path / "new" / base_name
    output.write_bytes(message)


def as_datetime(value: str) -> datetime:
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result


def mailbox_address(name: str, email: str) -> str:
    safe_name = name.replace('"', "'")
    return f'"{safe_name}" <{email}>'


def build_message(
    *,
    sender: dict[str, str],
    to: list[dict[str, str]],
    cc: list[dict[str, str]],
    subject: str,
    date: datetime,
    body: str,
    message_id: str,
    in_reply_to: str = "",
    references: list[str] | None = None,
    corpus: bool = False,
) -> bytes:
    message = MIMEText(body, "plain", "utf-8")
    message["From"] = mailbox_address(sender["name"], sender["email"])
    message["To"] = ", ".join(mailbox_address(person["name"], person["email"]) for person in to)
    if cc:
        message["Cc"] = ", ".join(mailbox_address(person["name"], person["email"]) for person in cc)
    message["Subject"] = subject
    message["Date"] = format_datetime(date)
    message["Message-ID"] = message_id
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    if references:
        message["References"] = " ".join(references)
    message["X-Mailer"] = "TechCorp Webmail"
    if corpus:
        message["X-Seed-Source"] = "EnronData.org / CMU CALO (anonymized)"
    return message.as_bytes()


def load_corpus_messages() -> list[dict[str, object]]:
    with gzip.open(MESSAGES_FILE, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def folder_path(user_email: str, folder: str) -> Path:
    base = maildir_name(user_email) / "Maildir"
    return base if folder.upper() == "INBOX" else base / f".{folder}"


def create_subscriptions_file(mailbox_base: Path, folders: set[str]) -> None:
    path = mailbox_base / "Maildir" / "subscriptions"
    path.write_text(
        "".join(f"{folder}\n" for folder in sorted(folders) if folder.upper() != "INBOX"),
        encoding="utf-8",
    )


def deliver_task_fixtures(
    legacy: dict[str, object],
    name_map: dict[str, str],
) -> int:
    count = 0
    for index, definition in enumerate(legacy["emails"]):
        sender_email = definition["from"]
        date = as_datetime(definition["date"])
        message = build_message(
            sender={"name": name_map.get(sender_email, sender_email.split("@")[0]), "email": sender_email},
            to=[{"name": name_map.get(email, email.split("@")[0]), "email": email} for email in definition.get("to", [])],
            cc=[],
            subject=definition["subject"],
            date=date,
            body=definition["body"],
            message_id=definition["message_id"],
            in_reply_to=definition.get("in_reply_to", ""),
            references=definition.get("references", []),
        )
        for user_email, delivery in definition["delivery"].items():
            write_maildir_message(
                folder_path(user_email, delivery["folder"]),
                message,
                delivery.get("flags", []),
                date,
                index,
            )
        count += 1
    return count


def deliver_corpus(primary_user: str, messages: list[dict[str, object]], start_index: int) -> None:
    for offset, definition in enumerate(messages):
        date = as_datetime(str(definition["date"]))
        message = build_message(
            sender=definition["from"],
            to=definition["to"],
            cc=definition.get("cc", []),
            subject=str(definition["subject"]),
            date=date,
            body=str(definition["body"]),
            message_id=str(definition["message_id"]),
            in_reply_to=str(definition.get("in_reply_to", "")),
            references=definition.get("references", []),
            corpus=True,
        )
        write_maildir_message(
            folder_path(primary_user, str(definition["folder"])),
            message,
            definition.get("flags", []),
            date,
            start_index + offset,
        )


def count_messages(user_email: str) -> int:
    root = maildir_name(user_email) / "Maildir"
    return sum(
        1
        for path in root.rglob("*")
        if path.is_file() and path.parent.name in {"cur", "new"}
    )


def main() -> int:
    legacy = json.loads(SEED_FILE.read_text(encoding="utf-8"))
    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))
    users = manifest["users"]
    primary_user = manifest["primary_user"]
    corpus_messages = load_corpus_messages()
    if len(corpus_messages) != manifest["corpus_message_count"]:
        raise RuntimeError("Corpus count does not match seed manifest")

    user_folders: dict[str, set[str]] = {user["email"]: set(STANDARD_FOLDERS) for user in users}
    for definition in legacy["emails"]:
        for user_email, delivery in definition["delivery"].items():
            if delivery["folder"].upper() != "INBOX":
                user_folders[user_email].add(delivery["folder"])
    for definition in corpus_messages:
        if str(definition["folder"]).upper() != "INBOX":
            user_folders[primary_user].add(str(definition["folder"]))

    for user in users:
        base = maildir_name(user["email"])
        ensure_maildir(base)
        for folder in user_folders[user["email"]]:
            ensure_maildir(base, folder)
        create_subscriptions_file(base, user_folders[user["email"]])

    name_map = {user["email"]: user["name"] for user in users}
    fixture_count = deliver_task_fixtures(legacy, name_map)
    deliver_corpus(primary_user, corpus_messages, fixture_count)

    output_dir = Path(os.environ.get("SEED_OUT_DIR", HERE / "configs"))
    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "dovecot-passwd").open("w", encoding="utf-8") as handle:
        for user in users:
            handle.write(f"{user['email']}:{{PLAIN}}{user['password']}::::\n")
    with (output_dir / "postfix-vmailbox").open("w", encoding="utf-8") as handle:
        for user in users:
            local = user["email"].split("@", 1)[0]
            handle.write(f"{user['email']}  {manifest['domain']}/{local}/Maildir/\n")

    print(f"Seeded {len(users)} login users, {fixture_count} task fixtures, and {len(corpus_messages)} corpus messages")
    for user in users:
        print(f"  {user['email']}: {count_messages(user['email'])} mailbox messages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build a deterministic, anonymized Thunderbird seed from one Enron mailbox.

The input is the extracted CMU CALO Maildir directory for ``shackleton-s``.
The output contains only the selected/anonymized sample, not the source corpus.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime
from pathlib import Path


SAMPLE_SIZE = 5_000
RECENT_THROUGH = datetime(2026, 7, 10, 17, 0, tzinfo=timezone.utc)
PRIMARY_EMAIL = "alice@techcorp.local"
PRIMARY_NAME = "Alice Chen"
PRIMARY_PASSWORD = "User@Secure123"
PRIMARY_SOURCE_MARKERS = ("sara.shackleton", "shackleton.sara")
CUSTODIANS_FILE = Path(__file__).with_name("enron_custodians.txt")
SOURCE_YEAR_MIN = 1997
SOURCE_YEAR_MAX = 2002
MAX_BODY_CHARS = 200_000

EMAIL_RE = re.compile(
    r"(?i)([a-z0-9][a-z0-9._%+/'=-]*@"
    r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?"
    r"(?:@[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?)*)"
)
SUBJECT_PREFIX_RE = re.compile(r"^\s*(?:(?:re|fw|fwd)\s*:\s*)+", re.IGNORECASE)
REPLY_SUBJECT_RE = re.compile(r"^\s*re\s*:", re.IGNORECASE)
QUOTED_HISTORY_MARKERS = (
    re.compile(r"(?im)^\s*-{2,}\s*Original Message\s*-{2,}\s*$"),
    re.compile(r"(?im)^\s*-{2,}\s*Forwarded Message\s*-{2,}\s*$"),
    re.compile(r"(?im)^\s*-{2,}\s*Forwarded by\b"),
    re.compile(r"(?im)^\s*Begin forwarded message:\s*$"),
    re.compile(r"(?im)^\s*On .{3,200} wrote:\s*$"),
)
LOTUS_HISTORY_RE = re.compile(
    r"(?ims)^\s*[A-Z][^\n]{1,100}\n"
    r"\s*\d{1,2}/\d{1,2}/\d{2,4}[^\n]*(?:AM|PM)\s*\n"
    r".{0,500}?^\s*To:\s*\S.*?^\s*Subject:\s*\S"
)
NAME_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'.-]+")

FIRST_NAMES = (
    "Avery", "Jordan", "Morgan", "Taylor", "Cameron", "Riley", "Parker", "Quinn",
    "Casey", "Rowan", "Emerson", "Hayden", "Reese", "Skyler", "Finley", "Blake",
    "Drew", "Harper", "Logan", "Micah", "Noel", "Payton", "Robin", "Sage",
    "Alex", "Jamie", "Kendall", "Lane", "Marley", "Nico", "River", "Shawn",
    "Terry", "Winter", "Bailey", "Dakota", "Ellis", "Frankie", "Gray", "Jules",
)
LAST_NAMES = (
    "Bennett", "Brooks", "Campbell", "Carter", "Collins", "Cooper", "Diaz", "Ellis",
    "Foster", "Garcia", "Gray", "Green", "Hall", "Hayes", "Howard", "Hughes",
    "James", "Kelly", "Kim", "Lee", "Lewis", "Martin", "Mitchell", "Morgan",
    "Morris", "Murphy", "Nelson", "Parker", "Patel", "Price", "Reed", "Rivera",
    "Roberts", "Ross", "Scott", "Stewart", "Turner", "Walker", "Ward", "Young",
    "Adams", "Allen", "Anderson", "Armstrong", "Baker", "Barnes", "Bell", "Brown",
    "Bryant", "Butler", "Clark", "Coleman", "Cook", "Cox", "Cruz", "Davis",
    "Edwards", "Evans", "Fisher", "Flores", "Ford", "Griffin", "Harris", "Henderson",
    "Hill", "Jackson", "Jenkins", "Johnson", "Jones", "King", "Long", "Lopez",
    "Marshall", "Martinez", "Mason", "Miller", "Moore", "Peterson", "Phillips", "Powell",
    "Richardson", "Robinson", "Rogers", "Russell", "Sanchez", "Sanders", "Simmons", "Smith",
    "Taylor", "Thomas", "Thompson", "Torres", "Watson", "White", "Williams", "Wilson",
    "Wood", "Wright", "Bailey", "Bishop", "Boyd", "Burke", "Chapman", "Crawford",
    "Dean", "Dunn", "Ferguson", "Franklin", "Gardner", "Gibson", "Graham", "Grant",
    "Hamilton",
)


@dataclass
class SourceMessage:
    path: Path
    date: datetime
    sender: tuple[str, str]
    to: list[tuple[str, str]]
    cc: list[tuple[str, str]]
    bcc: list[tuple[str, str]]
    subject: str
    body: str


def cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path, help="Extracted shackleton-s Maildir directory")
    parser.add_argument("output", type=Path, help="Seed asset output directory")
    parser.add_argument("--count", type=int, default=SAMPLE_SIZE)
    return parser.parse_args()


def normalize_address(value: str) -> str:
    value = value.strip().strip("<>(),;:\"'").lower()
    if value.startswith("mailto:"):
        value = value[7:]
    if "@" not in value or any(char.isspace() for char in value):
        return ""
    parts = value.split("@")
    local, domain = parts[0], parts[-1]
    if not local or not domain:
        return ""
    return f"{local}@{domain}"


def addresses(message: Message, header: str) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    seen: set[str] = set()
    for name, address in getaddresses(message.get_all(header, [])):
        address = normalize_address(address)
        if not address or address in seen:
            continue
        seen.add(address)
        parsed.append((str(name).strip(), address))
    return parsed


def extract_body(message: Message) -> str:
    parts: list[Message]
    if message.is_multipart():
        parts = [
            part
            for part in message.walk()
            if part.get_content_type() == "text/plain"
            and part.get_content_disposition() != "attachment"
        ]
        if not parts:
            parts = [
                part
                for part in message.walk()
                if part.get_content_maintype() == "text"
                and part.get_content_disposition() != "attachment"
            ]
    else:
        parts = [message]

    chunks: list[str] = []
    for part in parts:
        try:
            content = part.get_content()
        except Exception:
            payload = part.get_payload(decode=True) or b""
            content = payload.decode("utf-8", "replace")
        if isinstance(content, str):
            chunks.append(content)

    body = "\n\n".join(chunks).replace("\x00", "").strip()
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS].rstrip() + "\n\n[Long source message truncated]"
    return body


def strip_quoted_history(body: str, subject: str) -> str:
    """Keep a reply's new content and represent history through RFC headers.

    Enron's exported messages often paste the full parent message below an
    Outlook-style separator. Roundcube already understands In-Reply-To and
    References, so retaining that pasted copy makes a thread look like one
    giant flat message instead of a real email conversation.
    """
    if not REPLY_SUBJECT_RE.match(subject):
        return body

    cut_points = [
        match.start()
        for pattern in QUOTED_HISTORY_MARKERS
        if (match := pattern.search(body)) is not None
    ]

    # Some exports omit the separator but keep the Outlook header block.
    lines = body.splitlines(keepends=True)
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    for index, line in enumerate(lines):
        if not re.match(r"^\s*From:\s*\S", line, re.IGNORECASE):
            continue
        window = "".join(lines[index : index + 8])
        if re.search(r"(?im)^\s*(?:Sent|Date):\s*\S", window) and re.search(
            r"(?im)^\s*Subject:\s*\S", window
        ):
            cut_points.append(offsets[index])

    # Plain-text clients commonly quote the parent with consecutive > lines.
    quoted = re.search(r"(?m)^\s*>.*(?:\n\s*>.*)+", body)
    if quoted:
        cut_points.append(quoted.start())
    lotus_history = LOTUS_HISTORY_RE.search(body)
    if lotus_history:
        cut_points.append(lotus_history.start())

    if not cut_points:
        return body
    cleaned = body[: min(cut_points)].rstrip()
    return cleaned if cleaned else "(No additional reply text.)"


def parse_date(message: Message) -> datetime | None:
    try:
        value = parsedate_to_datetime(str(message.get("date", "")))
    except (TypeError, ValueError, OverflowError):
        return None
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    value = value.astimezone(timezone.utc)
    if not SOURCE_YEAR_MIN <= value.year <= SOURCE_YEAR_MAX:
        return None
    return value


def parse_message(path: Path) -> SourceMessage | None:
    message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    date = parse_date(message)
    sender = addresses(message, "from")
    if date is None or not sender:
        return None
    return SourceMessage(
        path=path,
        date=date,
        sender=sender[0],
        to=addresses(message, "to"),
        cc=addresses(message, "cc"),
        bcc=addresses(message, "bcc"),
        subject=str(message.get("subject", "(no subject)")).strip() or "(no subject)",
        body=extract_body(message),
    )


def semantic_key(message: SourceMessage) -> bytes:
    fields = [
        message.sender[1],
        ",".join(address for _, address in message.to),
        ",".join(address for _, address in message.cc),
        message.subject.casefold(),
        message.body.casefold(),
    ]
    return hashlib.sha256("\0".join(fields).encode("utf-8", "replace")).digest()


def load_sample(source: Path, count: int) -> list[SourceMessage]:
    if not source.is_dir():
        raise SystemExit(f"Source mailbox directory does not exist: {source}")

    unique: dict[bytes, SourceMessage] = {}
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.parent.name == "all_documents":
            continue
        parsed = parse_message(path)
        if parsed is None:
            continue
        unique.setdefault(semantic_key(parsed), parsed)

    if len(unique) < count:
        raise SystemExit(f"Only {len(unique)} usable unique messages; requested {count}")

    # The newest deterministic slice retains dense reply chains and produces a
    # realistic active mailbox instead of a uniform historical scatter.
    ordered = sorted(unique.values(), key=lambda item: (item.date, str(item.path)))
    return ordered[-count:]


def is_primary(address: str) -> bool:
    local = address.split("@", 1)[0]
    return any(marker in local for marker in PRIMARY_SOURCE_MARKERS)


def derive_name(address: str) -> str:
    local = address.split("@", 1)[0]
    tokens = [token.capitalize() for token in re.split(r"[._+\-/]+", local) if token.isalpha()]
    if len(tokens) >= 2:
        return " ".join(tokens[:3])
    return ""


def collect_identities(sample: list[SourceMessage]) -> tuple[set[str], dict[str, Counter[str]]]:
    all_addresses: set[str] = set()
    names: dict[str, Counter[str]] = defaultdict(Counter)
    for message in sample:
        for name, address in [message.sender, *message.to, *message.cc, *message.bcc]:
            all_addresses.add(address)
            if name and "@" not in name:
                names[address][name.strip()] += 1
        for line in (message.subject + "\n" + message.body).splitlines():
            for match in EMAIL_RE.finditer(line):
                address = normalize_address(match.group(1))
                all_addresses.add(address)
                before = line[: match.start()].rstrip(" \t<'")
                candidate = ""
                quoted = re.search(r'"([^"\n]{2,80})"\s*$', before)
                if quoted:
                    candidate = quoted.group(1)
                else:
                    comma_name = re.search(
                        r"([A-Z][A-Za-z'.-]+,\s*[A-Z][A-Za-z'.-]+(?:\s+[A-Z]\.?){0,2})\s*$",
                        before,
                    )
                    plain_name = re.search(
                        r"([A-Z][A-Za-z'.-]+(?:[ \t]+(?:[A-Z][A-Za-z'.-]+|[A-Z]\.)){1,4})\s*$",
                        before,
                    )
                    selected = comma_name or plain_name
                    if selected:
                        candidate = selected.group(1)
                candidate = re.sub(r"^(?:From|To|Cc|Bcc)\s*:\s*", "", candidate).strip()
                if candidate and len(NAME_TOKEN_RE.findall(candidate)) >= 2:
                    names[address][candidate] += 1
    all_addresses.discard("")
    return all_addresses, names


def add_canonical_custodians(
    all_addresses: set[str], names: dict[str, Counter[str]]
) -> int:
    count = 0
    for raw_line in CUSTODIANS_FILE.read_text(encoding="utf-8").splitlines():
        if not raw_line or raw_line.startswith("#"):
            continue
        custodian_id, custodian_name = raw_line.split("\t", 1)
        if custodian_id == "shackleton-s":
            address = "sara.shackleton@enron.com"
        else:
            surname_key = re.sub(r"[^a-z]", "", custodian_id.rsplit("-", 1)[0])
            candidates = [
                address
                for address in all_addresses
                if surname_key
                and surname_key in re.sub(r"[^a-z]", "", address.split("@", 1)[0])
            ]
            address = sorted(candidates)[0] if candidates else f"custodian-{custodian_id}@enron.invalid"
        all_addresses.add(address)
        names[address][custodian_name] += 100
        count += 1
    return count


def generated_identity(index: int) -> tuple[str, str, str, str]:
    capacity = len(FIRST_NAMES) * len(LAST_NAMES)
    if index >= capacity:
        raise ValueError(f"synthetic identity pool exhausted at {capacity} contacts")
    first = FIRST_NAMES[index % len(FIRST_NAMES)]
    last = LAST_NAMES[index // len(FIRST_NAMES)]
    email = f"{first.lower()}.{last.lower()}.{index + 1:04d}@techcorp.local"
    return f"{first} {last}", email, first, last


def build_identity_map(
    original_addresses: set[str], names: dict[str, Counter[str]]
) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    mapping: dict[str, dict[str, str]] = {}
    contacts: list[dict[str, str]] = []
    contact_index = 0
    for original in sorted(original_addresses):
        if is_primary(original):
            mapping[original] = {
                "name": PRIMARY_NAME,
                "email": PRIMARY_EMAIL,
                "firstname": "Alice",
                "surname": "Chen",
            }
            continue
        generated_name, generated_email, first, surname = generated_identity(contact_index)
        identity = {
            "name": generated_name,
            "email": generated_email,
            "firstname": first,
            "surname": surname,
        }
        mapping[original] = identity
        contacts.append(identity)
        contact_index += 1

    # A source alias may be absent from the selected headers but still belongs
    # to the chosen custodian; make the primary mapping explicit for auditing.
    mapping.setdefault(
        "sara.shackleton@enron.com",
        {"name": PRIMARY_NAME, "email": PRIMARY_EMAIL, "firstname": "Alice", "surname": "Chen"},
    )
    return mapping, contacts


def original_names(
    mapping: dict[str, dict[str, str]], observed_names: dict[str, Counter[str]]
) -> dict[str, str]:
    replacements: dict[str, str] = {
        "Sara Shackleton": PRIMARY_NAME,
        "Sara": "Alice",
        "Shackleton": "Chen",
    }
    for original, identity in mapping.items():
        candidates = set(observed_names.get(original, {}))
        derived = derive_name(original)
        if derived:
            candidates.add(derived)
            tokens = NAME_TOKEN_RE.findall(derived)
            if len(tokens) >= 2:
                candidates.add(f"{tokens[-1]}, {tokens[0]}")
        for candidate in candidates:
            candidate = " ".join(candidate.split())
            if len(candidate) < 4 or candidate.casefold() in {"unknown", "no address"}:
                continue
            replacements.setdefault(candidate, identity["name"])

    # First/last-name-only signatures are common. Replace a token only when it
    # resolves to one generated identity, avoiding inconsistent pseudonyms.
    token_targets: dict[str, set[str]] = defaultdict(set)
    for source_name, target_name in replacements.items():
        source_tokens = NAME_TOKEN_RE.findall(source_name)
        target_tokens = NAME_TOKEN_RE.findall(target_name)
        if len(source_tokens) < 2 or len(target_tokens) < 2:
            continue
        for source_token, target_token in ((source_tokens[0], target_tokens[0]), (source_tokens[-1], target_tokens[-1])):
            if len(source_token) >= 5:
                token_targets[source_token].add(target_token)
    for token, targets in token_targets.items():
        if len(targets) == 1:
            replacements.setdefault(token, next(iter(targets)))
    return replacements


def compile_name_pattern(replacements: dict[str, str]) -> re.Pattern[str] | None:
    names = sorted(replacements, key=lambda value: (-len(value), value.casefold()))
    if not names:
        return None
    return re.compile(
        r"(?<![A-Za-z])(?:" + "|".join(re.escape(name) for name in names) + r")(?![A-Za-z])",
        re.IGNORECASE,
    )


def anonymize(
    value: str,
    identities: dict[str, dict[str, str]],
    folded_name_replacements: dict[str, str],
    name_pattern: re.Pattern[str] | None,
) -> str:
    protected_emails: list[str] = []

    def protect_email(match: re.Match[str]) -> str:
        original = normalize_address(match.group(1))
        protected_emails.append(identities[original]["email"])
        return f"\ue000{len(protected_emails) - 1}\ue001"

    value = EMAIL_RE.sub(protect_email, value)
    if name_pattern is not None:
        value = name_pattern.sub(
            lambda match: folded_name_replacements[match.group(0).casefold()], value
        )
    # Keep body-level historical dates broadly aligned with the shifted headers.
    # Do this while generated addresses are protected so numeric address suffixes
    # such as ``.2001`` are never mistaken for source years.
    value = re.sub(
        r"\b(199[7-9]|200[0-2])\b",
        lambda match: str(int(match.group(1)) + 24),
        value,
    )
    value = re.sub(
        "\ue000([0-9]+)\ue001",
        lambda match: protected_emails[int(match.group(1))],
        value,
    )
    # Lotus Notes frequently appends a second directory suffix after an
    # address (for example ``<user@domain>@ENRON``). It is not part of the
    # Internet address matched above, but must not leak the source namespace.
    value = re.sub(r"(?i)@enron(?:\.com)?\b", " [TechCorp]", value)
    return value


def normalize_subject(subject: str) -> str:
    normalized = SUBJECT_PREFIX_RE.sub("", subject).strip().casefold()
    return re.sub(r"\s+", " ", normalized)


def person(identity: dict[str, str]) -> dict[str, str]:
    return {"name": identity["name"], "email": identity["email"]}


def convert_messages(
    sample: list[SourceMessage],
    identities: dict[str, dict[str, str]],
    name_replacements: dict[str, str],
) -> list[dict[str, object]]:
    latest = max(message.date for message in sample)
    date_shift = RECENT_THROUGH - latest
    name_pattern = compile_name_pattern(name_replacements)
    folded_name_replacements = {
        key.casefold(): replacement for key, replacement in name_replacements.items()
    }
    converted: list[dict[str, object]] = []
    thread_last: dict[str, tuple[str, list[str]]] = {}

    for index, source in enumerate(sample, 1):
        message_id = f"<corpus-{index:05d}@techcorp.local>"
        subject = anonymize(source.subject, identities, folded_name_replacements, name_pattern)
        reply_body = strip_quoted_history(source.body, source.subject)
        body = anonymize(reply_body, identities, folded_name_replacements, name_pattern)
        thread_key = normalize_subject(subject)
        in_reply_to = ""
        references: list[str] = []
        if SUBJECT_PREFIX_RE.match(subject) and thread_key in thread_last:
            previous_id, previous_references = thread_last[thread_key]
            in_reply_to = previous_id
            references = [*previous_references, previous_id][-20:]
        if thread_key:
            thread_last[thread_key] = (message_id, references)

        sender_identity = identities[source.sender[1]]
        converted.append(
            {
                "id": f"corpus-{index:05d}",
                "message_id": message_id,
                "from": person(sender_identity),
                "to": [person(identities[address]) for _, address in source.to],
                "cc": [person(identities[address]) for _, address in source.cc],
                "subject": subject,
                "date": (source.date + date_shift).isoformat(),
                "body": body,
                "folder": "Sent" if sender_identity["email"] == PRIMARY_EMAIL else "INBOX",
                "flags": [],
                "in_reply_to": in_reply_to,
                "references": references,
            }
        )

    # Most mail is read, the newest inbound slice remains unread, and inbound
    # messages followed by a sent message in the same thread are answered.
    latest_inbound = {
        message["id"]
        for message in [item for item in converted if item["folder"] == "INBOX"][-250:]
    }
    future_sent_threads: set[str] = set()
    for message in reversed(converted):
        key = normalize_subject(str(message["subject"]))
        flags: list[str] = []
        if message["id"] not in latest_inbound:
            flags.append("\\Seen")
        if message["folder"] == "INBOX" and key in future_sent_threads:
            flags.append("\\Answered")
        if message["folder"] == "Sent":
            future_sent_threads.add(key)
        message["flags"] = flags
    return converted


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_jsonl_gzip(path: Path, messages: list[dict[str, object]]) -> None:
    with path.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0, compresslevel=9) as archive:
            for message in messages:
                archive.write(json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
                archive.write(b"\n")


def main() -> int:
    args = cli()
    sample = load_sample(args.source, args.count)
    original_addresses, observed_names = collect_identities(sample)
    custodian_count = add_canonical_custodians(original_addresses, observed_names)
    identities, contacts = build_identity_map(original_addresses, observed_names)
    replacements = original_names(identities, observed_names)
    stripped_reply_count = sum(
        strip_quoted_history(message.body, message.subject) != message.body for message in sample
    )
    messages = convert_messages(sample, identities, replacements)

    # Existing task users stay valid; Alice is the anonymized selected custodian.
    users = [
        {"email": PRIMARY_EMAIL, "name": PRIMARY_NAME, "password": PRIMARY_PASSWORD, "role": "Legal Counsel"},
        {"email": "bob@techcorp.local", "name": "Bob Martin", "password": PRIMARY_PASSWORD, "role": "Project Manager"},
        {"email": "carol@techcorp.local", "name": "Carol White", "password": PRIMARY_PASSWORD, "role": "UX Designer"},
        {"email": "david@techcorp.local", "name": "David Kim", "password": PRIMARY_PASSWORD, "role": "QA Engineer"},
    ]
    # Keep the benchmark's original address book baseline intact. Bob and Carol
    # are deliberately absent because several benchmark tasks ask Alice to add
    # them as contacts. Every anonymized corpus participant is still included.
    contacts.sort(key=lambda contact: (contact["name"], contact["email"]))

    manifest = {
        "domain": "techcorp.local",
        "users": users,
        "primary_user": PRIMARY_EMAIL,
        "source": {
            "dataset": "CMU CALO Enron Email Dataset",
            "documentation": "http://enrondata.org/en/latest/data/calo-enron-email-dataset/",
            "custodian_id": "shackleton-s",
            "custodian_name": "Sara Shackleton",
            "anonymized_as": PRIMARY_NAME,
            "canonical_custodian_count": custodian_count,
        },
        "corpus_message_count": len(messages),
        "contact_count": len(contacts),
        "recent_through": RECENT_THROUGH.isoformat(),
        "threaded_reply_count": sum(bool(message["in_reply_to"]) for message in messages),
        "stripped_reply_history_count": stripped_reply_count,
    }

    args.output.mkdir(parents=True, exist_ok=True)
    write_json(args.output / "manifest.json", manifest)
    write_json(args.output / "contacts.json", contacts)
    write_jsonl_gzip(args.output / "messages.jsonl.gz", messages)

    print(
        f"Built {len(messages)} anonymized messages, "
        f"{manifest['threaded_reply_count']} threaded replies, and {len(contacts)} contacts"
    )
    print(f"Date range: {messages[0]['date']} .. {messages[-1]['date']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build additive Peppermint seed assets from the public GLPI project.

The existing Peppermint seed files are inputs only.  This script writes two
separate expansion assets so regenerating the GLPI corpus cannot rewrite or
reorder the original tickets or knowledge documents.

By default the script downloads recently updated GLPI issues and repository-
wide issue comments through GitHub's REST API.  Set GITHUB_TOKEN to raise the
API rate limit.  Documentation is read from a local checkout of
https://github.com/glpi-project/doc; pass --docs-dir to select that checkout.
"""

from __future__ import annotations

import argparse
import functools
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
BASE_TICKET_FILE = ROOT / "seed_data.json"
BASE_DOCUMENT_FILE = ROOT / "data" / "knowledge_base_documents.json"
DEFAULT_TICKET_OUTPUT = ROOT / "data" / "glpi_tickets.json"
DEFAULT_DOCUMENT_OUTPUT = ROOT / "data" / "glpi_knowledge_documents.json"
DEFAULT_USER_MAPPING_OUTPUT = ROOT / "data" / "glpi_user_mapping.json"

DEFAULT_REPOSITORY = "glpi-project/glpi"
DOC_REPOSITORY = "https://github.com/glpi-project/doc.git"
DOC_LICENSE = "CC BY-SA 3.0 FR"
DOC_LICENSE_URL = "https://creativecommons.org/licenses/by-sa/3.0/fr/deed.en"

TARGET_TOTAL_TICKETS = 1_000
TARGET_TOTAL_COMMENTS = 2_000
TARGET_TOTAL_DOCUMENTS = 200
TARGET_EXPANSION_USERS = 96

ROLE_ORDER = {"creator": 0, "assignee": 1, "commenter": 2}

EXPANSION_CLIENTS = (
    {
        "name": "Northstar Health Systems",
        "email": "helpdesk@northstar-health.peppermint.local",
        "contactName": "Avery Morgan",
        "number": "CL-1001",
    },
    {
        "name": "Harborview Logistics",
        "email": "support@harborview-logistics.peppermint.local",
        "contactName": "Jordan Wells",
        "number": "CL-1002",
    },
    {
        "name": "Meridian Education Group",
        "email": "it@meridian-education.peppermint.local",
        "contactName": "Casey Bennett",
        "number": "CL-1003",
    },
    {
        "name": "Pinecrest Financial Services",
        "email": "service@pinecrest-financial.peppermint.local",
        "contactName": "Riley Patel",
        "number": "CL-1004",
    },
    {
        "name": "Apex Manufacturing",
        "email": "operations@apex-manufacturing.peppermint.local",
        "contactName": "Cameron Diaz",
        "number": "CL-1005",
    },
    {
        "name": "Bluebird Hospitality",
        "email": "technology@bluebird-hospitality.peppermint.local",
        "contactName": "Taylor Brooks",
        "number": "CL-1006",
    },
    {
        "name": "CivicBridge Public Services",
        "email": "systems@civicbridge.peppermint.local",
        "contactName": "Morgan Reed",
        "number": "CL-1007",
    },
    {
        "name": "Lumen Retail Group",
        "email": "care@lumen-retail.peppermint.local",
        "contactName": "Quinn Foster",
        "number": "CL-1008",
    },
)

PSEUDONYM_FIRST_NAMES = (
    "Avery", "Bailey", "Cameron", "Casey", "Dakota", "Devon", "Drew", "Elliot",
    "Emerson", "Finley", "Harper", "Hayden", "Jamie", "Jesse", "Jordan", "Kai",
    "Kendall", "Lane", "Logan", "Micah", "Morgan", "Noel", "Parker", "Quinn",
    "Reese", "Remy", "Riley", "Robin", "Rowan", "Sage", "Skyler", "Taylor",
)

PSEUDONYM_LAST_NAMES = (
    "Adler", "Bennett", "Blair", "Brooks", "Campbell", "Carson", "Chen", "Clarke",
    "Collins", "Diaz", "Ellis", "Flynn", "Foster", "Grant", "Gray", "Hayes",
    "Hollis", "Keller", "Kim", "Lawson", "Morgan", "Nolan", "Patel", "Reed",
    "Rivera", "Sawyer", "Shaw", "Singh", "Stone", "Sutton", "Vega", "Wells",
)

BOT_LOGINS = {
    "github-actions",
    "github-actions[bot]",
    "dependabot[bot]",
    "renovate[bot]",
    "codecov[bot]",
}

REJECT_LABELS = {"duplicate", "invalid", "refused", "spam"}
HIGH_PRIORITY_LABELS = {"security", "performance", "regression", "complex issue"}
LOW_PRIORITY_LABELS = {"enhancement", "feature suggestion", "documentation"}
NEEDS_SUPPORT_LABELS = {"need feedback", "question", "support"}

DROP_ISSUE_SECTIONS = {
    "code of conduct",
    "is there an existing issue for this",
}

ISSUE_SECTION_TITLES = {
    "bug description": "Issue description",
    "description": "Issue description",
    "version": "Affected version",
    "steps to reproduce": "Reproduction steps",
    "steps to reproduce the behavior": "Reproduction steps",
    "expected behavior": "Expected behavior",
    "actual behavior": "Observed behavior",
    "page url": "Affected page",
    "relevant log output": "Diagnostic information",
    "your glpi setup information": "Environment details",
    "additional context": "Additional context",
    "anything else": "Additional context",
}

EMPTY_SECTION_VALUES = {
    "",
    "no response",
    "n/a",
    "not applicable",
    "[image omitted]",
    "[technical log or code excerpt omitted from the seed.]",
    "[extended diagnostic details omitted.]",
}


def parse_args() -> argparse.Namespace:
    base = json.loads(BASE_TICKET_FILE.read_text(encoding="utf-8"))
    base_docs = json.loads(BASE_DOCUMENT_FILE.read_text(encoding="utf-8"))["documents"]
    default_tickets = TARGET_TOTAL_TICKETS - len(base["tickets"])
    default_comments = TARGET_TOTAL_COMMENTS - sum(
        len(ticket.get("comments", [])) for ticket in base["tickets"]
    )
    default_docs = TARGET_TOTAL_DOCUMENTS - len(base_docs)

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", default=DEFAULT_REPOSITORY)
    parser.add_argument("--docs-dir", type=Path)
    parser.add_argument("--ticket-output", type=Path, default=DEFAULT_TICKET_OUTPUT)
    parser.add_argument("--document-output", type=Path, default=DEFAULT_DOCUMENT_OUTPUT)
    parser.add_argument(
        "--user-mapping-output", type=Path, default=DEFAULT_USER_MAPPING_OUTPUT
    )
    parser.add_argument("--cache-dir", type=Path)
    parser.add_argument("--ticket-count", type=int, default=default_tickets)
    parser.add_argument("--comment-count", type=int, default=default_comments)
    parser.add_argument("--document-count", type=int, default=default_docs)
    parser.add_argument("--open-pages", type=int, default=4)
    parser.add_argument("--closed-pages", type=int, default=10)
    parser.add_argument("--comment-pages", type=int, default=108)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Validate existing expansion outputs without downloading or writing.",
    )
    parser.add_argument(
        "--sanitize-existing",
        action="store_true",
        help=(
            "Rewrite only visible descriptions/comments in the existing ticket "
            "asset, preserving its selected issues, comments, users, and metadata."
        ),
    )
    parser.add_argument(
        "--assign-existing-clients",
        action="store_true",
        help=(
            "Add the deterministic client directory and client assignments to "
            "the existing ticket asset without changing corpus membership."
        ),
    )
    parser.add_argument(
        "--consolidate-existing-users",
        action="store_true",
        help=(
            "Consolidate source contributors with identical role combinations "
            "into shared personas in the existing assets without changing corpus "
            "membership."
        ),
    )
    return parser.parse_args()


def json_dump(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def client_email_for_issue(issue_number: Any) -> str | None:
    """Assign three quarters of imported issues across the client directory."""
    number = int(issue_number)
    if number % 4 == 0:
        return None
    return EXPANSION_CLIENTS[(number // 4) % len(EXPANSION_CLIENTS)]["email"]


def assign_clients_to_tickets(tickets: list[dict[str, Any]]) -> None:
    for ticket in tickets:
        client_email = client_email_for_issue(ticket["source"]["issueNumber"])
        if client_email:
            ticket["clientEmail"] = client_email
        else:
            ticket.pop("clientEmail", None)


class GitHubClient:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.token = os.environ.get("GITHUB_TOKEN")

    def request(self, path: str, params: dict[str, Any]) -> Any:
        query = urllib.parse.urlencode(params)
        url = f"https://api.github.com{path}?{query}"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "webarena-pro-peppermint-glpi-importer",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.load(response)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in {403, 429}:
                raise RuntimeError(
                    "GitHub API rate limit reached. Set GITHUB_TOKEN or rerun after "
                    f"the reset window. Response: {body[:300]}"
                ) from exc
            raise RuntimeError(f"GitHub request failed ({exc.code}): {body[:500]}") from exc

        return payload

    def get(self, path: str, params: dict[str, Any], cache_key: str) -> Any:
        cache_path = self.cache_dir / f"{cache_key}.json"
        if cache_path.exists():
            return json.loads(cache_path.read_text(encoding="utf-8"))
        payload = self.request(path, params)
        json_dump(cache_path, payload)
        return payload


def fetch_issue_candidates(
    client: GitHubClient,
    repository: str,
    state: str,
    pages: int,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for page in range(1, pages + 1):
        payload = client.get(
            "/search/issues",
            {
                "q": f"repo:{repository} is:issue state:{state}",
                "sort": "updated",
                "order": "desc",
                "per_page": 100,
                "page": page,
            },
            f"v2-search-issues-{state}-{page:02d}",
        )
        items = payload.get("items", [])
        if not items:
            break
        candidates.extend(items)
    return candidates


def fetch_recent_comments(
    client: GitHubClient,
    repository: str,
    pages: int,
) -> list[dict[str, Any]]:
    comments: list[dict[str, Any]] = []
    for page in range(1, pages + 1):
        payload = client.get(
            f"/repos/{repository}/issues/comments",
            {
                "sort": "created",
                "direction": "desc",
                "per_page": 100,
                "page": page,
            },
            f"v3-comments-{page:02d}",
        )
        if not payload:
            break
        comments.extend(payload)
    return comments


def label_names(issue: dict[str, Any]) -> set[str]:
    return {
        str(label.get("name", "")).strip().lower()
        for label in issue.get("labels", [])
        if label.get("name")
    }


def issue_number_from_url(url: str) -> int | None:
    match = re.search(r"/issues/(\d+)$", url or "")
    return int(match.group(1)) if match else None


def is_bot(user: dict[str, Any] | None) -> bool:
    if not user:
        return True
    login = str(user.get("login", "")).lower()
    return user.get("type") == "Bot" or login in BOT_LOGINS or login.endswith("[bot]")


def clean_markdown(value: str | None, limit: int) -> str:
    text = html.unescape(value or "")
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(
        r"```[^\n]*\n.*?```",
        "\n[Technical log or code excerpt omitted from the seed.]\n",
        text,
        flags=re.DOTALL,
    )
    text = re.sub(
        r"<details>.*?</details>",
        "\n[Extended diagnostic details omitted.]\n",
        text,
        flags=re.DOTALL | re.IGNORECASE,
    )
    text = re.sub(r"!\[([^]]*)]\([^)]+\)", r"[Image: \1]", text)
    text = re.sub(r"<img\b[^>]*>", "[Image omitted]", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>\n]+>", "", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email redacted]", text)
    text = re.sub(r"\r\n?", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > limit:
        text = text[: limit - 24].rstrip() + "\n\n[Content truncated.]"
    return text


def clean_helpdesk_text(
    value: str,
    limit: int,
    *,
    sanitize_visible_urls: bool = False,
    expand_escaped_newlines: bool = False,
) -> str:
    """Turn common GitHub Markdown into readable Peppermint plain text."""
    text = clean_markdown(value, limit * 2)
    text = re.sub(r"\[([^]]+)]\([^)]+\)", r"\1", text)
    if expand_escaped_newlines:
        text = re.sub(r"(?:\\+r)?\\+n", "\n", text)
        text = re.sub(r"\\+r", "\n", text)
    if sanitize_visible_urls:
        # Source URLs remain available in structured provenance metadata, but
        # should not leak into customer-facing ticket or comment copy.
        text = re.sub(r"https?://[^\s<>\[\]\"']*", "", text, flags=re.IGNORECASE)
        text = re.sub(
            r"^\s*(?:Reference|Source|Original public issue)\s*:\s*$",
            "",
            text,
            flags=re.MULTILINE | re.IGNORECASE,
        )
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*-\s*\[[xX ]\]\s*", "- ", text, flags=re.MULTILINE)
    text = re.sub(r"^(\s*)(\d+)\s*[-)]\s+", r"\1\2. ", text, flags=re.MULTILINE)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"^\s*\[(?:Image(?::[^]]*)?|Technical log or code excerpt omitted from the seed|Extended diagnostic details omitted)\.?]\s*$", "", text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > limit:
        text = text[: limit - 24].rstrip() + "\n\n[Content truncated.]"
    return text


def sanitize_existing_visible_text(value: str) -> str:
    """Remove visible source URLs and turn escaped newlines into line breaks."""
    text = re.sub(r"(?:\\+r)?\\+n", "\n", value)
    text = re.sub(r"\\+r", "\n", text)
    text = re.sub(r"https?://[^\s<>\[\]\"']*", "", text, flags=re.IGNORECASE)
    text = re.sub(
        r"^\s*(?:Reference|Source|Original public issue)\s*:\s*$",
        "",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    text = re.sub(r"[ \t]+(?=\n|$)", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def normalize_heading(value: str) -> str:
    value = clean_helpdesk_text(value, 200).strip().rstrip("?:")
    return re.sub(r"\s+", " ", value).lower()


def native_issue_title(value: str | None) -> str:
    title = clean_helpdesk_text(value or "", 240)
    # GitHub issue titles often carry a redundant product/version tag. The
    # source product and issue number remain in structured metadata.
    while True:
        cleaned = re.sub(
            r"^\s*\[\s*GLPI[^]]*]\s*(?:[-:–—]\s*)?",
            "",
            title,
            count=1,
            flags=re.IGNORECASE,
        ).strip()
        if cleaned == title:
            break
        title = cleaned
    return title or "Support request"


def section_is_empty(value: str) -> bool:
    normalized = re.sub(r"[_*]", "", value).strip().lower().rstrip(".")
    return normalized in EMPTY_SECTION_VALUES


def native_issue_detail(
    issue: dict[str, Any], *, sanitize_visible_content: bool = True
) -> str:
    """Translate a GitHub issue-template body into native helpdesk language."""
    body = clean_markdown(issue.get("body"), 12_000)
    sections: list[tuple[str | None, list[str]]] = []
    current_heading: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        nonlocal current_lines
        if current_heading is not None or current_lines:
            sections.append((current_heading, current_lines))
        current_lines = []

    for line in body.splitlines():
        heading_match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading_match:
            flush()
            current_heading = heading_match.group(1)
        else:
            current_lines.append(line)
    flush()

    rendered: list[str] = []
    for heading, lines in sections:
        normalized_heading = normalize_heading(heading or "")
        if normalized_heading in DROP_ISSUE_SECTIONS:
            continue

        content = clean_helpdesk_text(
            "\n".join(lines),
            5_000,
            sanitize_visible_urls=sanitize_visible_content,
            expand_escaped_newlines=sanitize_visible_content,
        )
        if normalized_heading == "disable plugins":
            if re.search(r"reproduce|disabled", content, flags=re.IGNORECASE):
                content = "The issue was reproduced with all plugins disabled."
            else:
                continue
            display_heading = "Troubleshooting performed"
        else:
            display_heading = ISSUE_SECTION_TITLES.get(
                normalized_heading,
                clean_helpdesk_text(heading or "Issue description", 120).rstrip("?:"),
            )

        if section_is_empty(content):
            continue
        rendered.append(f"{display_heading}:\n{content}")

    if not rendered:
        fallback = clean_helpdesk_text(
            body,
            5_500,
            sanitize_visible_urls=sanitize_visible_content,
            expand_escaped_newlines=sanitize_visible_content,
        )
        if fallback:
            rendered.append(f"Issue description:\n{fallback}")

    detail = "\n\n".join(rendered)
    if len(detail) > 6_000:
        detail = detail[: 5_976].rstrip() + "\n\n[Content truncated.]"
    return detail


def issue_is_usable(issue: dict[str, Any]) -> bool:
    labels = label_names(issue)
    title = native_issue_title(issue.get("title"))
    # Keep candidate selection stable when visible source URLs are removed.
    # This reproduces the prior eligibility calculation while the transformed
    # output uses the sanitized rendering below.
    body = native_issue_detail(issue, sanitize_visible_content=False)
    if labels & REJECT_LABELS:
        return False
    if not title or len(body) < 60:
        return False
    return True


def map_priority(labels: set[str]) -> str:
    if labels & HIGH_PRIORITY_LABELS:
        return "high"
    if labels & LOW_PRIORITY_LABELS:
        return "low"
    return "medium"


def map_type(labels: set[str]) -> str:
    if "security" in labels:
        return "incident"
    if "bug" in labels:
        return "bug"
    if labels & {"enhancement", "feature suggestion"}:
        return "feature"
    if "inventory" in labels:
        return "maintenance"
    return "support"


def map_status(issue: dict[str, Any], labels: set[str]) -> tuple[str, bool]:
    if issue.get("state") == "closed":
        return "done", True
    if labels & NEEDS_SUPPORT_LABELS:
        return "needs_support", False
    return "in_progress", False


def source_login(user: dict[str, Any] | None) -> str | None:
    if not user or not user.get("login"):
        return None
    return str(user["login"]).strip()


def issue_assignees(issue: dict[str, Any]) -> list[dict[str, Any]]:
    assignees = [user for user in issue.get("assignees", []) if source_login(user)]
    primary = issue.get("assignee")
    if primary and source_login(primary):
        primary_login = source_login(primary).casefold()
        assignees = [
            primary,
            *[
                user
                for user in assignees
                if source_login(user).casefold() != primary_login
            ],
        ]
    return assignees


def collect_actor_roles(
    selected: list[dict[str, Any]],
    allocated_comments: dict[int, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    actors: dict[str, dict[str, Any]] = {}

    def add(user: dict[str, Any] | None, role: str) -> None:
        login = source_login(user)
        if not login:
            return
        key = login.casefold()
        actor = actors.setdefault(key, {"sourceLogin": login, "roles": set()})
        actor["roles"].add(role)

    for issue in selected:
        add(issue.get("user"), "creator")
        for assignee in issue_assignees(issue):
            add(assignee, "assignee")
        for comment in allocated_comments.get(int(issue["number"]), []):
            add(comment.get("user"), "commenter")
    return actors


def build_actor_mapping(
    actor_roles: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    capacity = len(PSEUDONYM_FIRST_NAMES) * len(PSEUDONYM_LAST_NAMES)
    target_users = min(TARGET_EXPANSION_USERS, len(actor_roles))
    if target_users > capacity:
        raise RuntimeError(
            f"Pseudonym pool supports {capacity} users but corpus needs {target_users}"
        )

    grouped: dict[tuple[str, ...], list[str]] = defaultdict(list)
    for key, actor in actor_roles.items():
        signature = tuple(sorted(actor["roles"], key=ROLE_ORDER.__getitem__))
        grouped[signature].append(key)

    signatures = sorted(
        grouped,
        key=lambda roles: tuple(ROLE_ORDER[role] for role in roles),
    )
    if target_users < len(signatures):
        raise RuntimeError(
            f"Cannot preserve {len(signatures)} role combinations with only "
            f"{target_users} personas"
        )

    total_actors = len(actor_roles)
    quotas = {
        signature: len(grouped[signature]) * target_users / total_actors
        for signature in signatures
    }
    allocations = {
        signature: max(1, int(quotas[signature]))
        for signature in signatures
    }
    while sum(allocations.values()) < target_users:
        candidates = [
            signature
            for signature in signatures
            if allocations[signature] < len(grouped[signature])
        ]
        signature = min(
            candidates,
            key=lambda item: (
                -(quotas[item] - allocations[item]),
                tuple(ROLE_ORDER[role] for role in item),
            ),
        )
        allocations[signature] += 1
    while sum(allocations.values()) > target_users:
        candidates = [
            signature for signature in signatures if allocations[signature] > 1
        ]
        signature = min(
            candidates,
            key=lambda item: (
                -(allocations[item] - quotas[item]),
                tuple(ROLE_ORDER[role] for role in item),
            ),
        )
        allocations[signature] -= 1

    mapping: dict[str, dict[str, Any]] = {}
    persona_index = 0
    for signature in signatures:
        personas: list[dict[str, Any]] = []
        for _ in range(allocations[signature]):
            first = PSEUDONYM_FIRST_NAMES[
                persona_index % len(PSEUDONYM_FIRST_NAMES)
            ]
            last = PSEUDONYM_LAST_NAMES[
                persona_index // len(PSEUDONYM_FIRST_NAMES)
            ]
            personas.append(
                {
                    "personaId": f"persona-{persona_index + 1:03d}",
                    "roles": list(signature),
                    "name": f"{first} {last}",
                    "email": f"{first.lower()}.{last.lower()}@peppermint.local",
                }
            )
            persona_index += 1

        for index, key in enumerate(sorted(grouped[signature])):
            actor = actor_roles[key]
            persona = personas[index % len(personas)]
            mapping[key] = {
                "sourceLogin": actor["sourceLogin"],
                **persona,
            }

    assert persona_index == target_users
    return mapping


def mapped_actor(
    user: dict[str, Any] | None,
    actor_mapping: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    login = source_login(user)
    if not login or login.casefold() not in actor_mapping:
        raise RuntimeError(f"Source actor is missing from mapping: {login!r}")
    return actor_mapping[login.casefold()]


@functools.lru_cache(maxsize=4)
def actor_mention_pattern(keys: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(
        r"@(" + "|".join(re.escape(key) for key in keys) + r")(?![\w-])",
        flags=re.IGNORECASE,
    )


def replace_actor_mentions(
    value: str,
    actor_mapping: dict[str, dict[str, Any]],
) -> str:
    if "@" not in value:
        return value
    keys = tuple(sorted(actor_mapping, key=len, reverse=True))
    pattern = actor_mention_pattern(keys)
    return pattern.sub(
        lambda match: actor_mapping[match.group(1).casefold()]["name"],
        value,
    )


def comment_by_issue(
    raw_comments: Iterable[dict[str, Any]],
) -> dict[int, list[dict[str, Any]]]:
    grouped: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for comment in raw_comments:
        number = issue_number_from_url(str(comment.get("issue_url", "")))
        body = clean_markdown(comment.get("body"), 2_500)
        if number is None or not body or is_bot(comment.get("user")):
            continue
        grouped[number].append(comment)
    for comments in grouped.values():
        comments.sort(key=lambda item: (item.get("created_at", ""), item.get("id", 0)))
    return grouped


def select_issues(
    open_candidates: list[dict[str, Any]],
    closed_candidates: list[dict[str, Any]],
    grouped_comments: dict[int, list[dict[str, Any]]],
    target: int,
) -> list[dict[str, Any]]:
    def ranking(issue: dict[str, Any]) -> tuple[int, int, str, int]:
        number = int(issue["number"])
        return (
            len(grouped_comments.get(number, [])),
            int(issue.get("comments", 0)),
            str(issue.get("updated_at", "")),
            number,
        )

    usable_open = [issue for issue in open_candidates if issue_is_usable(issue)]
    usable_closed = [issue for issue in closed_candidates if issue_is_usable(issue)]
    usable_open.sort(key=ranking, reverse=True)
    usable_closed.sort(key=ranking, reverse=True)

    # The public tracker currently has roughly 366 open issues. Preserve as much
    # of that live queue as possible, then fill the expansion with resolved,
    # comment-rich issues. This gives Peppermint both actionable and historical
    # ticket states without touching the original 118 records.
    selected_open = usable_open[: min(366, target)]
    selected = selected_open + usable_closed[: target - len(selected_open)]
    if len(selected) < target:
        raise RuntimeError(
            f"Only {len(selected)} usable issues were available; need {target}. "
            "Increase --closed-pages or provide GITHUB_TOKEN."
        )
    return selected


def allocate_comments(
    selected: list[dict[str, Any]],
    grouped_comments: dict[int, list[dict[str, Any]]],
    target: int,
) -> dict[int, list[dict[str, Any]]]:
    allocation: dict[int, list[dict[str, Any]]] = defaultdict(list)
    issue_numbers = [int(issue["number"]) for issue in selected]
    max_depth = max((len(grouped_comments.get(number, [])) for number in issue_numbers), default=0)

    # Round-robin by thread depth so many tickets retain discussion context
    # instead of allowing a few unusually long threads to consume the corpus.
    for depth in range(max_depth):
        for number in issue_numbers:
            comments = grouped_comments.get(number, [])
            if depth < len(comments):
                allocation[number].append(comments[depth])
                if sum(len(items) for items in allocation.values()) == target:
                    return allocation

    available = sum(len(items) for items in allocation.values())
    raise RuntimeError(
        f"Only {available} usable comments matched selected issues; need {target}. "
        "Increase --comment-pages and, if necessary, --closed-pages."
    )


def transform_comment(
    comment: dict[str, Any],
    actor_mapping: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    user = comment.get("user") or {}
    login = str(user.get("login") or "unknown-contributor")
    actor = mapped_actor(user, actor_mapping)
    created = str(comment.get("created_at") or "")[:10]
    body = clean_helpdesk_text(
        comment.get("body") or "",
        2_500,
        sanitize_visible_urls=True,
        expand_escaped_newlines=True,
    )
    body = replace_actor_mentions(body, actor_mapping)
    source_url = str(comment.get("html_url") or "")
    text = f"{body}\n\nOriginal response date: {created}"
    return {
        "userEmail": actor["email"],
        "text": text,
        "public": True,
        "source": {
            "project": DEFAULT_REPOSITORY,
            "commentId": comment.get("id"),
            "author": login,
            "anonymizedAuthorEmail": actor["email"],
            "url": source_url,
            "createdAt": comment.get("created_at"),
        },
    }


def transform_issue(
    issue: dict[str, Any],
    allocated_comments: list[dict[str, Any]],
    repository: str,
    actor_mapping: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    labels = label_names(issue)
    status, is_complete = map_status(issue, labels)
    reporter_user = issue.get("user") or {}
    reporter = str(reporter_user.get("login") or "unknown-reporter")
    creator = mapped_actor(reporter_user, actor_mapping)
    assignees = issue_assignees(issue)
    anonymized_assignees = [
        mapped_actor(assignee, actor_mapping) for assignee in assignees
    ]
    source_url = str(issue.get("html_url") or "")
    detail = replace_actor_mentions(native_issue_detail(issue), actor_mapping)
    title = replace_actor_mentions(native_issue_title(issue.get("title")), actor_mapping)

    ticket: dict[str, Any] = {
        "title": title,
        "detail": detail,
        "priority": map_priority(labels),
        "type": map_type(labels),
        "createdByEmail": creator["email"],
        "status": status,
        "isComplete": is_complete,
        "comments": [
            transform_comment(comment, actor_mapping)
            for comment in allocated_comments
        ],
        "source": {
            "project": repository,
            "issueNumber": issue.get("number"),
            "url": source_url,
            "author": reporter,
            "anonymizedAuthorEmail": creator["email"],
            "assignees": [
                {
                    "sourceLogin": source_login(source_assignee),
                    "anonymizedEmail": anonymized_assignee["email"],
                }
                for source_assignee, anonymized_assignee in zip(
                    assignees, anonymized_assignees
                )
            ],
            "labels": sorted(labels),
            "state": issue.get("state"),
            "stateReason": issue.get("state_reason"),
            "createdAt": issue.get("created_at"),
            "updatedAt": issue.get("updated_at"),
            "closedAt": issue.get("closed_at"),
        },
    }
    if anonymized_assignees:
        # Peppermint has one assignedTo relation. Preserve every upstream
        # assignee in source metadata and map the primary assignee into the UI.
        ticket["assignedTo"] = anonymized_assignees[0]["email"]
    client_email = client_email_for_issue(issue.get("number"))
    if client_email:
        ticket["clientEmail"] = client_email
    return ticket


def expansion_users(
    actor_mapping: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    personas: dict[str, dict[str, Any]] = {}
    for actor in actor_mapping.values():
        persona = personas.setdefault(
            actor["personaId"],
            {
                "personaId": actor["personaId"],
                "name": actor["name"],
                "email": actor["email"],
                "roles": actor["roles"],
                "sourceLogins": [],
            },
        )
        persona["sourceLogins"].append(actor["sourceLogin"])

    return [
        {
            "name": persona["name"],
            "email": persona["email"],
            "password": "Password1!",
            "admin": False,
            "source": {
                "project": DEFAULT_REPOSITORY,
                "personaId": persona["personaId"],
                "logins": sorted(persona["sourceLogins"], key=str.casefold),
                "roles": persona["roles"],
            },
        }
        for persona in sorted(personas.values(), key=lambda item: item["personaId"])
    ]


def user_mapping_payload(
    actor_mapping: dict[str, dict[str, Any]],
    generated_at: str,
) -> dict[str, Any]:
    users = [
        {
            "sourceLogin": actor["sourceLogin"],
            "roles": actor["roles"],
            "personaId": actor["personaId"],
            "anonymizedName": actor["name"],
            "anonymizedEmail": actor["email"],
        }
        for key in sorted(actor_mapping)
        for actor in (actor_mapping[key],)
    ]
    seed_users = expansion_users(actor_mapping)
    return {
        "version": "1.1",
        "generatedAt": generated_at,
        "source": {
            "project": DEFAULT_REPOSITORY,
            "repositoryUrl": f"https://github.com/{DEFAULT_REPOSITORY}",
        },
        "totalUsers": len(seed_users),
        "totalSourceUsers": len(users),
        "totalAnonymizedUsers": len(seed_users),
        "roleCounts": {
            role: sum(role in user["roles"] for user in users)
            for role in ("creator", "assignee", "commenter")
        },
        "consolidation": {
            "strategy": "exact-role-combination",
            "targetAnonymizedUsers": TARGET_EXPANSION_USERS,
        },
        "users": users,
    }


def replace_anonymized_names(value: str, replacements: dict[str, str]) -> str:
    if not replacements:
        return value
    folded = {old.casefold(): new for old, new in replacements.items()}
    pattern = re.compile(
        r"(" + "|".join(
            re.escape(name) for name in sorted(replacements, key=len, reverse=True)
        ) + r")",
        flags=re.IGNORECASE,
    )
    return pattern.sub(lambda match: folded[match.group(1).casefold()], value)


def consolidate_existing_users(
    ticket_payload: dict[str, Any],
    mapping_payload: dict[str, Any],
) -> dict[str, Any]:
    old_users = mapping_payload["users"]
    actor_roles = {
        user["sourceLogin"].casefold(): {
            "sourceLogin": user["sourceLogin"],
            "roles": set(user["roles"]),
        }
        for user in old_users
    }
    old_by_login = {
        user["sourceLogin"].casefold(): user for user in old_users
    }
    actor_mapping = build_actor_mapping(actor_roles)
    name_replacements = {
        old_by_login[key]["anonymizedName"]: actor["name"]
        for key, actor in actor_mapping.items()
        if old_by_login[key]["anonymizedName"] != actor["name"]
    }

    for ticket in ticket_payload["tickets"]:
        source = ticket["source"]
        creator = actor_mapping[source["author"].casefold()]
        ticket["createdByEmail"] = creator["email"]
        source["anonymizedAuthorEmail"] = creator["email"]
        ticket["title"] = replace_anonymized_names(
            ticket["title"], name_replacements
        )
        ticket["detail"] = replace_anonymized_names(
            ticket["detail"], name_replacements
        )

        for assignee in source["assignees"]:
            actor = actor_mapping[assignee["sourceLogin"].casefold()]
            assignee["anonymizedEmail"] = actor["email"]
        if source["assignees"]:
            primary_login = source["assignees"][0]["sourceLogin"].casefold()
            ticket["assignedTo"] = actor_mapping[primary_login]["email"]
        else:
            ticket.pop("assignedTo", None)

        for comment in ticket.get("comments", []):
            comment_source = comment["source"]
            commenter = actor_mapping[comment_source["author"].casefold()]
            comment["userEmail"] = commenter["email"]
            comment_source["anonymizedAuthorEmail"] = commenter["email"]
            comment["text"] = replace_anonymized_names(
                comment["text"], name_replacements
            )

    seed_users = expansion_users(actor_mapping)
    ticket_payload["users"] = seed_users
    ticket_payload["selection"]["sourceContributors"] = len(actor_mapping)
    ticket_payload["selection"]["anonymizedUsers"] = len(seed_users)
    return user_mapping_payload(actor_mapping, mapping_payload["generatedAt"])


def checkout_docs(path: Path | None) -> tuple[Path, str, bool]:
    if path:
        root = path.resolve()
        temporary = False
    else:
        root = Path(tempfile.mkdtemp(prefix="glpi-doc-")) / "repo"
        subprocess.run(
            ["git", "clone", "--depth", "1", DOC_REPOSITORY, str(root)],
            check=True,
        )
        temporary = True

    source = root / "source"
    if not source.is_dir():
        raise RuntimeError(f"GLPI documentation source directory not found: {source}")
    revision = subprocess.check_output(
        ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
    ).strip()
    return root, revision, temporary


def clean_rst_inline(text: str) -> str:
    text = re.sub(r":\w+(?::\w+)?:`([^`<>]+)(?:\s*<[^>]+>)?`", r"\1", text)
    text = re.sub(r"`([^`<>]+)(?:\s*<[^>]+>)?`_?", r"\1", text)
    text = text.replace("**", "").replace("*", "").replace("``", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def parse_rst(path: Path) -> tuple[str, list[dict[str, Any]]]:
    raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    lines: list[str] = []
    skip_indented = False
    for raw in raw_lines:
        stripped = raw.strip()
        if stripped.startswith(".. _") or stripped.startswith(".. |"):
            continue
        if stripped.startswith(".. image::") or stripped.startswith(".. figure::"):
            skip_indented = True
            continue
        if skip_indented and (not raw.startswith((" ", "\t")) or not stripped):
            skip_indented = False
        if skip_indented or stripped.startswith(":"):
            continue
        lines.append(raw.rstrip())

    sections: list[dict[str, Any]] = []
    title = ""
    current_title = "Overview"
    current: list[str] = []
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if not paragraph:
            return
        value = clean_rst_inline(" ".join(paragraph))
        paragraph.clear()
        if value and not value.startswith(".. ") and value != "::":
            current.append(value)

    def flush_section() -> None:
        flush_paragraph()
        if current:
            sections.append({"title": current_title, "items": current.copy()})
            current.clear()

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
        is_heading = bool(
            stripped
            and next_line
            and len(next_line) >= 3
            and re.fullmatch(r"([=\-~^\"'])\1{2,}", next_line)
        )
        if is_heading:
            flush_section()
            heading = clean_rst_inline(stripped)
            if not title:
                title = heading
            else:
                current_title = heading
            i += 2
            continue

        if not stripped:
            flush_paragraph()
        elif stripped.startswith(("* ", "- ", "+ ")):
            flush_paragraph()
            value = clean_rst_inline(stripped[2:])
            if value:
                current.append(value)
        elif re.match(r"^\d+[.)]\s+", stripped):
            flush_paragraph()
            current.append(clean_rst_inline(re.sub(r"^\d+[.)]\s+", "", stripped)))
        elif stripped.startswith(".. ") or stripped.startswith(".. toctree::"):
            pass
        else:
            paragraph.append(stripped)
        i += 1
    flush_section()
    return title or path.stem.replace("_", " ").title(), sections


def doc_rank(relative: Path) -> tuple[int, str]:
    value = relative.as_posix().lower()
    priorities = (
        "modules/assistance/",
        "modules/administration/",
        "modules/configuration/",
        "modules/tools/",
        "modules/assets/",
        "modules/management/",
        "modules/user-settings/",
        "advanced/",
        "tabs/",
    )
    for index, prefix in enumerate(priorities):
        if value.startswith(prefix):
            return index, value
    return len(priorities), value


def build_documents(doc_root: Path, revision: str, target: int) -> list[dict[str, Any]]:
    source_root = doc_root / "source"
    candidates: list[tuple[Path, str, list[dict[str, Any]]]] = []
    for path in source_root.rglob("*.rst"):
        relative = path.relative_to(source_root)
        if path.name.lower() == "index.rst" or "/index.rst" in relative.as_posix().lower():
            continue
        title, sections = parse_rst(path)
        body_size = sum(len(item) for section in sections for item in section["items"])
        if body_size < 250:
            continue
        candidates.append((relative, title, sections))

    candidates.sort(key=lambda item: doc_rank(item[0]))
    if len(candidates) < target:
        raise RuntimeError(f"Only {len(candidates)} usable GLPI documents found; need {target}")

    documents: list[dict[str, Any]] = []
    for index, (relative, title, sections) in enumerate(candidates[:target], start=1):
        source_url = (
            "https://github.com/glpi-project/doc/blob/"
            f"{revision}/source/{relative.as_posix()}"
        )
        trimmed_sections: list[dict[str, Any]] = []
        remaining = 8_000
        for section in sections[:10]:
            items: list[str] = []
            for item in section["items"]:
                if remaining <= 0:
                    break
                value = item[: min(1_200, remaining)].strip()
                if value:
                    items.append(value)
                    remaining -= len(value)
            if items:
                trimmed_sections.append({"title": section["title"], "items": items})
            if remaining <= 0:
                break

        summary = next(
            (item for section in trimmed_sections for item in section["items"] if len(item) >= 40),
            f"GLPI user documentation for {title}.",
        )
        parts = relative.parts
        category = parts[1] if len(parts) > 2 and parts[0] == "modules" else parts[0]
        tags = ["glpi", "documentation", category, relative.stem.replace("_", "-")]
        documents.append(
            {
                "id": f"GLPI-DOC-{index:04d}",
                "title": title,
                "category": category,
                "tags": list(dict.fromkeys(tags)),
                "relatedIssuePatterns": [category, relative.stem.replace("_", "-")],
                "summary": summary[:700],
                "sections": trimmed_sections,
                "attribution": (
                    "Adapted from the GLPI user documentation by GLPI contributors. "
                    f"Licensed {DOC_LICENSE}. Source: {source_url}"
                ),
                "source": {
                    "project": "glpi-project/doc",
                    "path": f"source/{relative.as_posix()}",
                    "revision": revision,
                    "url": source_url,
                    "license": DOC_LICENSE,
                    "licenseUrl": DOC_LICENSE_URL,
                },
            }
        )
    return documents


def validate_assets(
    ticket_file: Path,
    document_file: Path,
    user_mapping_file: Path,
    expected_tickets: int,
    expected_comments: int,
    expected_documents: int,
) -> None:
    tickets_payload = json.loads(ticket_file.read_text(encoding="utf-8"))
    documents_payload = json.loads(document_file.read_text(encoding="utf-8"))
    user_mapping_payload_data = json.loads(
        user_mapping_file.read_text(encoding="utf-8")
    )
    tickets = tickets_payload["tickets"]
    seed_users = tickets_payload["users"]
    clients = tickets_payload["clients"]
    documents = documents_payload["documents"]
    mapped_users = user_mapping_payload_data["users"]
    comments = sum(len(ticket.get("comments", [])) for ticket in tickets)

    assert len(tickets) == expected_tickets, (len(tickets), expected_tickets)
    assert comments == expected_comments, (comments, expected_comments)
    assert len(documents) == expected_documents, (len(documents), expected_documents)
    assert len({ticket["source"]["issueNumber"] for ticket in tickets}) == len(tickets)
    comment_ids = [
        comment["source"]["commentId"]
        for ticket in tickets
        for comment in ticket.get("comments", [])
    ]
    assert len(set(comment_ids)) == len(comment_ids)
    assert len({document["id"] for document in documents}) == len(documents)
    assert clients == [dict(client) for client in EXPANSION_CLIENTS]
    assert len({client["name"] for client in clients}) == len(clients)
    assert len({client["email"] for client in clients}) == len(clients)
    assert len({client["number"] for client in clients}) == len(clients)
    client_emails = {client["email"] for client in clients}
    assigned_client_emails = {
        ticket["clientEmail"] for ticket in tickets if ticket.get("clientEmail")
    }
    assert assigned_client_emails == client_emails
    assert any(ticket.get("clientEmail") is None for ticket in tickets)
    assert all(
        ticket.get("clientEmail") == client_email_for_issue(
            ticket["source"]["issueNumber"]
        )
        for ticket in tickets
    )
    assert user_mapping_payload_data["totalUsers"] == len(seed_users)
    assert user_mapping_payload_data["totalSourceUsers"] == len(mapped_users)
    assert user_mapping_payload_data["totalAnonymizedUsers"] == len(seed_users)
    assert len(seed_users) == min(TARGET_EXPANSION_USERS, len(mapped_users))
    assert tickets_payload["selection"]["sourceContributors"] == len(mapped_users)
    assert tickets_payload["selection"]["anonymizedUsers"] == len(seed_users)
    assert user_mapping_payload_data["consolidation"] == {
        "strategy": "exact-role-combination",
        "targetAnonymizedUsers": TARGET_EXPANSION_USERS,
    }
    assert len({user["sourceLogin"].casefold() for user in mapped_users}) == len(mapped_users)
    mapped_emails = {user["anonymizedEmail"] for user in mapped_users}
    assert len(mapped_emails) == len(seed_users)
    assert len({user["anonymizedName"] for user in mapped_users}) == len(seed_users)
    assert len({user["email"] for user in seed_users}) == len(seed_users)
    assert len({user["name"] for user in seed_users}) == len(seed_users)
    assert {user["email"] for user in seed_users} == mapped_emails

    mapped_by_email: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for user in mapped_users:
        mapped_by_email[user["anonymizedEmail"]].append(user)
    seed_by_email = {user["email"]: user for user in seed_users}
    for email, source_users in mapped_by_email.items():
        seed_user = seed_by_email[email]
        assert {user["anonymizedName"] for user in source_users} == {
            seed_user["name"]
        }
        assert {user["personaId"] for user in source_users} == {
            seed_user["source"]["personaId"]
        }
        role_signatures = {tuple(user["roles"]) for user in source_users}
        assert role_signatures == {tuple(seed_user["source"]["roles"])}
        assert {
            user["sourceLogin"].casefold() for user in source_users
        } == {
            login.casefold() for login in seed_user["source"]["logins"]
        }

    assert all(ticket["createdByEmail"] in mapped_emails for ticket in tickets)
    assert all(
        "assignedTo" not in ticket or ticket["assignedTo"] in mapped_emails
        for ticket in tickets
    )
    assert all(
        comment["userEmail"] in mapped_emails
        for ticket in tickets
        for comment in ticket.get("comments", [])
    )

    expected_roles: dict[str, set[str]] = defaultdict(set)
    for ticket in tickets:
        expected_roles[ticket["source"]["author"].casefold()].add("creator")
        for assignee in ticket["source"]["assignees"]:
            expected_roles[assignee["sourceLogin"].casefold()].add("assignee")
        for comment in ticket.get("comments", []):
            expected_roles[comment["source"]["author"].casefold()].add("commenter")
    actual_roles = {
        user["sourceLogin"].casefold(): set(user["roles"])
        for user in mapped_users
    }
    assert actual_roles == expected_roles
    assert user_mapping_payload_data["roleCounts"] == {
        role: sum(role in roles for roles in actual_roles.values())
        for role in ("creator", "assignee", "commenter")
    }
    mapped_by_login = {
        user["sourceLogin"].casefold(): user for user in mapped_users
    }
    for ticket in tickets:
        source = ticket["source"]
        creator = mapped_by_login[source["author"].casefold()]
        assert ticket["createdByEmail"] == creator["anonymizedEmail"]
        assert source["anonymizedAuthorEmail"] == creator["anonymizedEmail"]
        for assignee in source["assignees"]:
            mapped_assignee = mapped_by_login[assignee["sourceLogin"].casefold()]
            assert assignee["anonymizedEmail"] == mapped_assignee["anonymizedEmail"]
        if source["assignees"]:
            primary = mapped_by_login[
                source["assignees"][0]["sourceLogin"].casefold()
            ]
            assert ticket["assignedTo"] == primary["anonymizedEmail"]
        else:
            assert "assignedTo" not in ticket
        for comment in ticket.get("comments", []):
            comment_source = comment["source"]
            commenter = mapped_by_login[comment_source["author"].casefold()]
            assert comment["userEmail"] == commenter["anonymizedEmail"]
            assert (
                comment_source["anonymizedAuthorEmail"]
                == commenter["anonymizedEmail"]
            )
    assert all(ticket["status"] in {"needs_support", "in_progress", "done"} for ticket in tickets)
    assert all(ticket["priority"] in {"low", "medium", "high"} for ticket in tickets)
    assert all(ticket.get("source", {}).get("url") for ticket in tickets)
    assert all(not ticket["title"].lower().startswith("[glpi") for ticket in tickets)
    assert all("Imported from GLPI issue" not in ticket["detail"] for ticket in tickets)
    assert all("Original reporter:" not in ticket["detail"] for ticket in tickets)
    assert all("GLPI labels:" not in ticket["detail"] for ticket in tickets)
    assert all("### Code of Conduct" not in ticket["detail"] for ticket in tickets)
    assert all(
        not re.search(r"https?://", ticket["detail"], flags=re.IGNORECASE)
        for ticket in tickets
    )
    assert all(
        "\\n" not in ticket["detail"]
        for ticket in tickets
    )
    assert all(
        not re.search(r"https?://", comment["text"], flags=re.IGNORECASE)
        for ticket in tickets
        for comment in ticket.get("comments", [])
    )
    assert all(
        "\\n" not in comment["text"]
        for ticket in tickets
        for comment in ticket.get("comments", [])
    )
    assert all(document.get("source", {}).get("license") == DOC_LICENSE for document in documents)


def main() -> int:
    args = parse_args()
    if args.consolidate_existing_users:
        ticket_payload = json.loads(args.ticket_output.read_text(encoding="utf-8"))
        mapping_payload = json.loads(
            args.user_mapping_output.read_text(encoding="utf-8")
        )
        updated_mapping = consolidate_existing_users(
            ticket_payload, mapping_payload
        )
        json_dump(args.ticket_output, ticket_payload)
        json_dump(args.user_mapping_output, updated_mapping)
        validate_assets(
            args.ticket_output,
            args.document_output,
            args.user_mapping_output,
            args.ticket_count,
            args.comment_count,
            args.document_count,
        )
        print(
            f"Consolidated {updated_mapping['totalSourceUsers']} source users "
            f"into {updated_mapping['totalAnonymizedUsers']} role-matched personas "
            "without changing corpus membership."
        )
        return 0

    if args.assign_existing_clients:
        payload = json.loads(args.ticket_output.read_text(encoding="utf-8"))
        payload["clients"] = [dict(client) for client in EXPANSION_CLIENTS]
        assign_clients_to_tickets(payload["tickets"])
        json_dump(args.ticket_output, payload)
        validate_assets(
            args.ticket_output,
            args.document_output,
            args.user_mapping_output,
            args.ticket_count,
            args.comment_count,
            args.document_count,
        )
        assigned_count = sum(
            bool(ticket.get("clientEmail")) for ticket in payload["tickets"]
        )
        print(
            f"Added {len(payload['clients'])} clients and assigned "
            f"{assigned_count} existing imported tickets without changing "
            "corpus membership."
        )
        return 0

    if args.sanitize_existing:
        payload = json.loads(args.ticket_output.read_text(encoding="utf-8"))
        for ticket in payload["tickets"]:
            ticket["detail"] = sanitize_existing_visible_text(ticket["detail"])
            for comment in ticket.get("comments", []):
                comment["text"] = sanitize_existing_visible_text(comment["text"])
        json_dump(args.ticket_output, payload)
        validate_assets(
            args.ticket_output,
            args.document_output,
            args.user_mapping_output,
            args.ticket_count,
            args.comment_count,
            args.document_count,
        )
        print(
            f"Sanitized visible content for {len(payload['tickets'])} existing "
            "tickets without changing corpus membership."
        )
        return 0

    if args.check_only:
        validate_assets(
            args.ticket_output,
            args.document_output,
            args.user_mapping_output,
            args.ticket_count,
            args.comment_count,
            args.document_count,
        )
        print("GLPI expansion assets are valid.")
        return 0

    cache_dir = args.cache_dir or Path(tempfile.mkdtemp(prefix="peppermint-glpi-api-"))
    client = GitHubClient(cache_dir)
    print(f"Fetching GLPI issues into cache {cache_dir} ...")
    open_candidates = fetch_issue_candidates(
        client, args.repository, "open", args.open_pages
    )
    closed_candidates = fetch_issue_candidates(
        client, args.repository, "closed", args.closed_pages
    )
    raw_comments = fetch_recent_comments(client, args.repository, args.comment_pages)
    grouped = comment_by_issue(raw_comments)
    selected = select_issues(open_candidates, closed_candidates, grouped, args.ticket_count)
    allocated = allocate_comments(selected, grouped, args.comment_count)
    actor_roles = collect_actor_roles(selected, allocated)
    actor_mapping = build_actor_mapping(actor_roles)
    seed_users = expansion_users(actor_mapping)
    tickets = [
        transform_issue(
            issue,
            allocated[int(issue["number"])],
            args.repository,
            actor_mapping,
        )
        for issue in selected
    ]

    doc_root, doc_revision, _temporary = checkout_docs(args.docs_dir)
    documents = build_documents(doc_root, doc_revision, args.document_count)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    ticket_payload = {
        "version": "1.0",
        "generatedAt": generated_at,
        "generatedFor": "Peppermint additive data expansion",
        "source": {
            "project": args.repository,
            "repositoryUrl": f"https://github.com/{args.repository}",
            "api": "GitHub REST API",
        },
        "selection": {
            "tickets": len(tickets),
            "comments": sum(len(ticket["comments"]) for ticket in tickets),
            "sourceContributors": len(actor_mapping),
            "anonymizedUsers": len(seed_users),
            "open": sum(not ticket["isComplete"] for ticket in tickets),
            "closed": sum(ticket["isComplete"] for ticket in tickets),
            "originalPeppermintTicketsPreserved": True,
        },
        "clients": [dict(client) for client in EXPANSION_CLIENTS],
        "users": seed_users,
        "tickets": tickets,
    }
    document_payload = {
        "version": "1.0",
        "generatedAt": generated_at,
        "generatedFor": "Peppermint additive GLPI knowledge expansion",
        "totalDocuments": len(documents),
        "source": {
            "project": "glpi-project/doc",
            "repositoryUrl": DOC_REPOSITORY.removesuffix(".git"),
            "revision": doc_revision,
            "license": DOC_LICENSE,
            "licenseUrl": DOC_LICENSE_URL,
        },
        "documents": documents,
    }
    mapping_payload = user_mapping_payload(actor_mapping, generated_at)

    json_dump(args.ticket_output, ticket_payload)
    json_dump(args.document_output, document_payload)
    json_dump(args.user_mapping_output, mapping_payload)
    validate_assets(
        args.ticket_output,
        args.document_output,
        args.user_mapping_output,
        args.ticket_count,
        args.comment_count,
        args.document_count,
    )
    print(
        f"Wrote {len(tickets)} tickets, {args.comment_count} comments, "
        f"{len(documents)} documents, and {len(seed_users)} anonymized personas "
        f"for {len(actor_mapping)} source contributors."
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

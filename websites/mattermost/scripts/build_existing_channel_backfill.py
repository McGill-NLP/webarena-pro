#!/usr/bin/env python3
"""Build a topic-matched dataset backfill for the original 20 channels.

Messages come verbatim from the public Software-related Slack Chats with
Disentangled Conversations corpus. Whole source conversations are retained as
Mattermost threads. Source participant names are deterministically mapped to
members of the destination team.

The generated posts carry their original dataset timestamps in ``props``. Run
``finalize_task_ready_seed.sql`` after importing the seed to apply those fixed
timestamps, trim the task user's channel membership, and establish the bounded
unread state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


MAX_MESSAGE_CHARS = 16_000
SEED_BATCH = "existing-channel-backfill-v1"
REPOSITORY = (
    "https://github.com/preethac/"
    "Software-related-Slack-Chats-with-Disentangled-Conversations"
)


@dataclass(frozen=True)
class Topic:
    team: str
    channel: str
    keywords: tuple[str, ...]


TOPICS = (
    Topic(
        "engineering",
        "project-alpha",
        (
            "project", "sprint", "milestone", "roadmap", "feature", "ticket",
            "requirement", "deadline", "release", "product",
        ),
    ),
    Topic(
        "engineering",
        "project-beta",
        (
            "architecture", "frontend", "dashboard", "component", "state",
            "model", "design", "framework", "application", "interface",
        ),
    ),
    Topic(
        "engineering",
        "deployments",
        (
            "deploy", "deployment", "release", "production", "version",
            "rollback", "build", "server", "environment", "configuration",
        ),
    ),
    Topic(
        "engineering",
        "code-reviews",
        (
            "pull request", "code review", "review", "commit", "merge", "github",
            "git ", "refactor", "diff", "branch",
        ),
    ),
    Topic(
        "engineering",
        "bugs-and-issues",
        (
            "bug", "error", "exception", "failure", "failed", "crash", "issue",
            "fix", "debug", "broken", "problem",
        ),
    ),
    Topic(
        "engineering",
        "standup-notes",
        (
            "today", "yesterday", "tomorrow", "working on", "worked on",
            "blocker", "blocked", "progress", "this week", "next week",
        ),
    ),
    Topic(
        "engineering",
        "tech-discussions",
        (
            "api", "language", "function", "type", "library", "framework",
            "architecture", "protocol", "implementation", "programming",
        ),
    ),
    Topic(
        "engineering",
        "devops",
        (
            "docker", "kubernetes", "server", "cluster", "database", "postgres",
            "continuous integration", " ci ", "pipeline", "cloud", "infrastructure",
        ),
    ),
    Topic(
        "engineering",
        "security-alerts",
        (
            "security", "authentication", "authorization", "password", "vulnerability",
            "attack", "permission", "encrypt", "token", "credential",
        ),
    ),
    Topic(
        "marketing",
        "campaigns",
        (
            "launch", "campaign", "adoption", "community", "announce", "promotion",
            "audience", "user", "conference", "release",
        ),
    ),
    Topic(
        "marketing",
        "social-media",
        (
            "twitter", "social", "reddit", "blog", "post", "share", "link",
            "community", "public", "online",
        ),
    ),
    Topic(
        "marketing",
        "analytics",
        (
            "analytics", "data", "metric", "performance", "benchmark", "statistics",
            "count", "rate", "measure", "report",
        ),
    ),
    Topic(
        "marketing",
        "content-calendar",
        (
            "documentation", "docs", "guide", "tutorial", "example", "blog",
            "article", "write", "publish", "content",
        ),
    ),
    Topic(
        "marketing",
        "design-requests",
        (
            "design", " ui ", " ux ", "css", "layout", "color", "image", "graphic",
            "font", "svg", "visual",
        ),
    ),
    Topic(
        "general",
        "announcements",
        (
            "announce", "announcement", "released", "new version", "available",
            "launch", "update", "news", "published", "welcome",
        ),
    ),
    Topic(
        "general",
        "random",
        (
            "interesting", "anyone", "thought", "idea", "curious", "thanks",
            "question", "wonder", "cool", "discussion",
        ),
    ),
    Topic(
        "general",
        "watercooler",
        (
            "coffee", "food", "drink", "lunch", "weekend", "music", "game",
            "fun", "restaurant", "beer", "pizza",
        ),
    ),
    Topic(
        "general",
        "events",
        (
            "conference", "meetup", "event", "talk", "workshop", "schedule",
            "session", "presentation", "attend", "speaker",
        ),
    ),
    Topic(
        "general",
        "help-desk",
        (
            "help", "how do", "how can", "anyone know", "problem", "issue",
            "trying to", "does anyone", "question", "error",
        ),
    ),
    Topic(
        "general",
        "new-joiners",
        (
            "beginner", "new to", "getting started", "learn", "tutorial", "hello",
            "first time", "newbie", "introduction", "welcome",
        ),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset_root", type=Path)
    parser.add_argument(
        "--base-seed",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "seed_data.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "existing_channel_backfill_seed.json",
    )
    parser.add_argument("--messages-per-channel", type=int, default=250)
    return parser.parse_args()


def normalized_text(text: str) -> str:
    return " " + re.sub(r"\s+", " ", text.lower()) + " "


def keyword_score(text: str, topic: Topic) -> int:
    return sum(text.count(keyword) for keyword in topic.keywords)


def source_timestamp_ms(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def iter_conversations(dataset_root: Path):
    data_dir = dataset_root / "data"
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Missing dataset directory: {data_dir}")

    for xml_path in sorted(data_dir.rglob("*.xml")):
        conversations: dict[str, list[dict[str, str]]] = defaultdict(list)
        for _, element in ET.iterparse(xml_path, events=("end",)):
            if element.tag != "message":
                continue
            conversation_id = element.attrib.get("conversation_id", "")
            text = element.findtext("text") or ""
            timestamp = element.findtext("ts") or ""
            source_user = element.findtext("user") or "Unknown"
            if (
                conversation_id
                and text.strip()
                and timestamp
                and len(text) <= MAX_MESSAGE_CHARS
            ):
                conversations[conversation_id].append(
                    {"timestamp": timestamp, "source_user": source_user, "text": text}
                )
            element.clear()

        relative_path = xml_path.relative_to(dataset_root)
        for conversation_id, messages in conversations.items():
            messages.sort(key=lambda message: message["timestamp"])
            yield f"{relative_path}:{conversation_id}", messages


def classify(dataset_root: Path):
    candidates: dict[str, list[tuple[int, str, list[dict[str, str]]]]] = defaultdict(list)
    for source_id, messages in iter_conversations(dataset_root):
        searchable = normalized_text("\n".join(message["text"] for message in messages))
        for topic in TOPICS:
            score = keyword_score(searchable, topic)
            if score:
                candidates[topic.channel].append((score, source_id, messages))

    for topic in TOPICS:
        candidates[topic.channel].sort(key=lambda item: (-item[0], item[1]))
    return candidates


def team_usernames(base_seed: dict, team_name: str) -> list[str]:
    team = next(team for team in base_seed["teams"] if team["name"] == team_name)
    members = team["members"]
    if members == "__all__":
        return [user["username"] for user in base_seed["users"]]
    return list(members)


def mapped_user(source_user: str, usernames: list[str]) -> str:
    digest = hashlib.sha256(source_user.encode("utf-8")).digest()
    return usernames[int.from_bytes(digest[:4], "big") % len(usernames)]


def message_props(source_id: str, message: dict[str, str]) -> dict:
    return {
        "seed_batch": SEED_BATCH,
        "seed_source": "software-slack-corpus",
        "source_conversation": source_id,
        "source_user": message["source_user"],
        "source_timestamp": message["timestamp"],
        "source_create_at_ms": source_timestamp_ms(message["timestamp"]),
    }


def build_channel_post(
    source_id: str, messages: list[dict[str, str]], usernames: list[str]
) -> dict:
    first = messages[0]
    root = {
        "user": mapped_user(first["source_user"], usernames),
        "message": first["text"],
        "props": message_props(source_id, first),
    }
    if len(messages) > 1:
        root["replies"] = [
            {
                "user": mapped_user(message["source_user"], usernames),
                "message": message["text"],
                "props": message_props(source_id, message),
            }
            for message in messages[1:]
        ]
    return root


def select_conversations(candidates, target: int, globally_used: set[str]):
    selected = []
    message_count = 0
    for score, source_id, messages in candidates:
        if message_count >= target:
            break
        if source_id in globally_used:
            continue
        globally_used.add(source_id)
        selected.append((score, source_id, messages))
        message_count += len(messages)
    return selected, message_count


def build_recent_emma_dm(candidates, used: set[str]) -> tuple[dict, str]:
    """Create fixed recent-interaction evidence required by two cross-site tasks."""
    for _, source_id, messages in candidates:
        searchable = normalized_text("\n".join(message["text"] for message in messages))
        is_casual = any(
            keyword in searchable
            for keyword in (" coffee", " lunch", " weekend", " restaurant", " beer", " pizza")
        )
        contains_code = "```" in searchable or "&lt;" in searchable
        if (
            source_id in used
            or not 2 <= len(messages) <= 6
            or not is_casual
            or contains_code
        ):
            continue
        used.add(source_id)
        fixed_start = 1_777_636_800_000  # 2026-05-01 12:00:00 UTC
        # Keep this task-state conversation deliberately short: two messages
        # are enough to make Emma the unambiguous most recent interaction.
        selected_messages = messages[-2:]
        source_start_index = len(messages) - len(selected_messages)
        dm_messages = []
        for index, message in enumerate(selected_messages):
            source_index = source_start_index + index
            author = "emma.davis" if index == len(selected_messages) - 1 else "admin"
            props = message_props(source_id, message)
            props["source_create_at_ms"] = fixed_start + source_index * 1_000
            props["fixed_task_timestamp"] = True
            if index == len(selected_messages) - 1:
                props["task_evidence_key"] = "recent-emma-interaction"
            dm_messages.append(
                {"user": author, "message": message["text"], "props": props}
            )
        return {
            "participants": ["admin", "emma.davis"],
            "messages": dm_messages,
        }, source_id
    raise RuntimeError("No short, unused watercooler conversation available for Emma DM")


def build_seed(base_seed: dict, candidates, target: int) -> tuple[dict, dict]:
    conversations: dict[str, dict[str, list[dict]]] = defaultdict(dict)
    stats = {}
    used: set[str] = set()

    for topic in TOPICS:
        selected, message_count = select_conversations(
            candidates[topic.channel], target, used
        )
        if message_count < target:
            raise RuntimeError(
                f"{topic.channel} has only {message_count} unique relevant messages; "
                f"target is {target}"
            )
        usernames = team_usernames(base_seed, topic.team)
        conversations[topic.team][topic.channel] = [
            build_channel_post(source_id, messages, usernames)
            for _, source_id, messages in selected
        ]
        stats[f"{topic.team}/{topic.channel}"] = {
            "conversations": len(selected),
            "messages": message_count,
            "minimum_keyword_score": min(score for score, _, _ in selected),
        }

    emma_dm, emma_source = build_recent_emma_dm(candidates["watercooler"], used)
    seed = {
        "admin": base_seed["admin"],
        "users": base_seed["users"],
        "teams": base_seed["teams"],
        "channels": {},
        "conversations": conversations,
        "direct_messages": [emma_dm],
        "group_messages": [],
        "dataset_provenance": {
            "name": "Software-related Slack Chats with Disentangled Conversations",
            "repository": REPOSITORY,
            "message_text_policy": "verbatim",
            "participant_mapping": "deterministic mapping to destination-team users",
            "seed_batch": SEED_BATCH,
            "target_messages_per_channel": target,
            "recent_emma_dm_source": emma_source,
            "stats": stats,
        },
    }
    return seed, stats


def main() -> int:
    args = parse_args()
    base_seed = json.loads(args.base_seed.read_text())
    candidates = classify(args.dataset_root.resolve())
    seed, stats = build_seed(base_seed, candidates, args.messages_per_channel)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(seed, indent=2, ensure_ascii=False) + "\n")

    print(f"{'channel':38} {'messages':>9} {'threads':>8} {'min score':>9}")
    print("-" * 69)
    for channel, values in stats.items():
        print(
            f"{channel:38} {values['messages']:9,d} "
            f"{values['conversations']:8,d} {values['minimum_keyword_score']:9,d}"
        )
    print(f"\nWrote {args.output} ({args.output.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

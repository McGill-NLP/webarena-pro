#!/usr/bin/env python3
"""Build the durable Mattermost task-to-message evidence tables.

The CSV is the canonical exact table. The Markdown file is a readable index and
contains the same protected-message catalog. This script deliberately reads
task hints, not rubrics, and validates every protected original message against
``seed_data.json`` before writing either artifact.
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path


MATTERMOST_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = MATTERMOST_DIR.parents[1]
CONFIG_DIR = REPO_ROOT / "webarena-pro/src/webarena_pro/config"


@dataclass(frozen=True)
class EvidenceSpec:
    evidence_id: str
    team: str
    channel: str
    author: str
    needle: str
    post_id: str
    create_at_ms: int
    newest_rank: int
    original_synthetic: bool = True


EVIDENCE_SPECS = (
    EvidenceSpec("E01", "engineering", "deployments", "bob.wilson", "Weekly Deployment Schedule", "zs7apgtgpfn3bnxr9cxznwjpry", 1773126778323, 4),
    EvidenceSpec("E02", "engineering", "project-alpha", "kevin.martinez", "auth flow working end-to-end", "suwnzum7ppn5tbeag1ga6k1r7w", 1773126776742, 17),
    EvidenceSpec("E03", "marketing", "analytics", "ivy.chen", "Weekly Marketing Analytics Report", "i9a9qqzfginezb1o6b8a3siuoh", 1773126780759, 4),
    EvidenceSpec("E04", "marketing", "analytics", "ivy.chen", "312 demo requests from 3,200 views", "hhigzptwetywzb3g7hhhhjdw8e", 1773126780837, 1),
    EvidenceSpec("E05", "engineering", "code-reviews", "charlie.brown", "Need a review on PR #287", "rtdewtn5ein8uqwxqjq71jkiqh", 1773126778453, 9),
    EvidenceSpec("E06", "engineering", "code-reviews", "charlie.brown", "Max 3 retries, starting at 1s", "rrdusfgbf3gf7qrahwjai64wuw", 1773126778880, 7),
    EvidenceSpec("E07", "engineering", "project-beta", "kevin.martinez", "key metrics we need to display", "u9b7ehb3kbnz5dkohhn3s6rt9y", 1773126777967, 3),
    EvidenceSpec("E08", "general", "watercooler", "grace.lee", "Korean fried chicken", "dmpbf4epffrkmd9biy83m5qitw", 1773126782132, 5),
    EvidenceSpec("E09", "general", "events", "henry.taylor", "Upcoming Events", "8p613yhn3tr5zjiuy8ebxazfih", 1773126782274, 7),
    EvidenceSpec("E10", "general", "events", "henry.taylor", "20 spots for the food bank", "7c9cox7rttg4bb1jx4fmrrmz8h", 1773126782472, 1),
    EvidenceSpec("E11", "general", "announcements", "henry.taylor", "Onboarding buddy assignments", "zj5n1igz83g7bnoujg81u9c9kh", 1773126781324, 11),
    EvidenceSpec("E12", "engineering", "devops", "bob.wilson", "Infrastructure Status Report", "bfyx5zu8k7b45mkmhe4ex4srwc", 1773126780069, 5),
    EvidenceSpec("E13", "engineering", "devops", "bob.wilson", "PostgreSQL connection pool exhaustion", "czed4ajgb7byjbpg854mikegzy", 1773126780117, 3),
    EvidenceSpec("E14", "engineering", "project-alpha", "diana.prince", "QA Report for Sprint 11", "cm7g4nhuyjbq9fr1furyz7emph", 1773126777636, 5),
    EvidenceSpec("E15", "engineering", "project-beta", "jane.smith", "architecture planning for Project Beta", "oq4um7bawtd48fr4tfchj6zkce", 1773126777779, 9),
    EvidenceSpec("E16", "engineering", "tech-discussions", "lisa.wang", "quarterly dependency audit", "zgcemj5typgct8zb5mh4a7kxue", 1773126779959, 4),
    EvidenceSpec("E17", "marketing", "campaigns", "emma.davis", "Q1 Campaign Results", "duk3c7xk9bnemr57t3kda66zwh", 1773126780499, 5),
    EvidenceSpec("E18", "engineering", "security-alerts", "lisa.wang", "Security Incident Report", "4hnjptbpmpnmzgdqdth51qxt3y", 1773126780203, 5),
)


TASK_EVIDENCE = {
    "20260503184339354488": ("E01",),
    "20260503185315769328": ("E02",),
    "20260503190213766807": ("E03", "E04"),
    "20260503190832065620": ("E05", "E06"),
    "20260504075257262372": ("E07",),
    "20260505042726105357": ("E01",),
    "20260505064034296257": ("E19",),
    "20260505065327650216": ("E19",),
    "20260505074859037077": ("E19",),
    "20260505145825226718": ("E08",),
    "20260505154727372812": ("E03", "E04"),
    "20260505154917503199": ("E09", "E10"),
    "20260505155117644963": ("E11",),
    "20260505155400345653": ("E05", "E06"),
    "20260505155812814340": ("E12",),
    "20260505173610008785": ("E07",),
}


LEGACY_EVIDENCE = {
    "0.json": ("E11",),
    "1.json": ("E01",),
    "2.json": ("E14",),
    "3.json": ("E15",),
    "4.json": ("E16",),
    "5.json": ("E17",),
    "6.json": ("E18",),
    "7.json": ("E12", "E13"),
    "8.json": ("E09",),
    "9.json": ("E03", "E04"),
}


STATE_NOTES = {
    "20260501095702013727": "No source post: Mattermost is the destination. DM Jane Smith with the externally found recruit Henry Okonkwo (henry@example.com).",
    "20260501161040287155": "No source post: create a DM to jane.smith and send the externally created Notion publication link.",
    "20260501164621147802": "No source post: create a group DM containing admin, Emma Davis, and Frank Miller; the YouTube-derived answer is violin.",
    "20260502082525279373": "No source post: Jane Smith is the Mattermost destination; the external Q3 Engineering value is 180000.",
    "20260502132211002201": "No source post: Jane Smith is the Mattermost destination; the external total Q3 budget is 360000.",
    "20260504052746189076": "State only: TechCorp General supplies Alice, Bob, John, and Ivy; create HR team and share its invite in a group DM.",
    "20260504052844732934": "State only: Project Alpha and Project Beta currently have 11 unique members including admin; preserve their memberships for the union invite.",
    "20260504052919118470": "State only: final seed deliberately has 8 unread messages across 8 joined conversations, so the count is below 20.",
    "20260504052950707272": "State only: Project Alpha and Project Beta are existing destinations; Project Charlie invitees are Kevin, Bob, Jane, Lisa, and Mike.",
    "20260504054529893474": "No source post. The unstable word 'tomorrow' is fixed to May 5, 2026 from the May 4 task timestamp; options remain 2 PM, 4 PM, and 6 PM.",
    "20260504072531188863": "State only: Project Alpha, Project Beta, devops, code-reviews, bugs-and-issues, and deployments exist. Admin is kept in 14 team channels (17 conversations including DM/GMs), below 20.",
    "20260504072600984958": "State only: Marketing members are admin, Emma, Frank, Grace, Ivy, and Kevin; remove Emma and Grace, then promote/message the remaining non-admin members.",
    "20260504074404058060": "No source post: Emma Davis and Bob Wilson are call/DM destinations.",
    "20260504183129492900": "Profile state: Mattermost has exactly 16 seeded users including admin; external combined answer is 46 contacts no.",
    "20260504185849691654": "Profile state: Mattermost has exactly 16 seeded users including admin; external combined answer is 46 contacts no.",
    "20260505064034296257": "E19 is the newest fixed admin DM interaction, authored by Emma Davis; send her the Notion publication link.",
    "20260505065327650216": "E19 is the newest fixed admin DM interaction, authored by Emma Davis; send her the Notion publication link.",
    "20260505074859037077": "E19 establishes Emma Davis as the Mattermost recent contact. Required profiles: emma.davis@techcorp.com and john.doe@techcorp.com.",
    "20260505082541044452": "No source post: Emma Davis is the Mattermost availability/itinerary destination.",
    "20260505144604025951": "State only: use the existing group DM containing admin, jane.smith, john.doe, and kevin.martinez; email admin@techcorp.com, jane.smith@techcorp.com, and kevin.martinez@techcorp.com.",
    "20260505153151050026": "Profile state: henry.taylor@techcorp.com, mike.ross@techcorp.com, john.doe@techcorp.com, and ivy.chen@techcorp.com; DM each after emailing.",
    "20260505155054845830": "Profile state: diana.prince@techcorp.com, emma.davis@techcorp.com, jane.smith@techcorp.com, and henry.taylor@techcorp.com; Henry is also the DM destination.",
    "20260505195624631109": "No source post: Mike Ross is the DM destination; the external Acidwave answer is Lighthouse.",
    "20260505214616690665": "No source post is required; Mattermost is only one of the sites searched for Leon Green's contact, which is found in Nextcloud.",
    "20260506000534325746": "No source post: Mike Ross is the DM destination; the external Acidwave answer is Trailer Static.",
}


def flatten_seed_messages(seed: dict):
    for team, channels in seed["conversations"].items():
        for channel, roots in channels.items():
            for root in roots:
                yield team, channel, root["user"], root["message"]
                for reply in root.get("replies", []):
                    yield team, channel, reply["user"], reply["message"]


def protected_evidence(seed: dict, backfill: dict) -> dict[str, dict]:
    flattened = list(flatten_seed_messages(seed))
    result = {}
    for spec in EVIDENCE_SPECS:
        matches = [
            message
            for team, channel, author, message in flattened
            if team == spec.team
            and channel == spec.channel
            and author == spec.author
            and spec.needle.lower() in message.lower()
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"{spec.evidence_id}: expected exactly one seed match, found {len(matches)}"
            )
        exact_message = matches[0]
        result[spec.evidence_id] = {
            "evidence_id": spec.evidence_id,
            "post_id": spec.post_id,
            "team": spec.team,
            "channel": spec.channel,
            "author": spec.author,
            "create_at_ms": spec.create_at_ms,
            "original_newest_rank": spec.newest_rank,
            "original_synthetic": True,
            "sha256": hashlib.sha256(exact_message.encode()).hexdigest(),
            "exact_message": exact_message,
        }

    emma_messages = backfill["direct_messages"][0]["messages"]
    emma_message = next(
        message
        for message in emma_messages
        if message.get("props", {}).get("task_evidence_key")
        == "recent-emma-interaction"
    )
    exact_message = emma_message["message"]
    result["E19"] = {
        "evidence_id": "E19",
        "post_id": "props:task_evidence_key=recent-emma-interaction",
        "team": "",
        "channel": "DM admin + emma.davis",
        "author": "emma.davis",
        "create_at_ms": emma_message["props"]["source_create_at_ms"],
        "original_newest_rank": 1,
        "original_synthetic": False,
        "sha256": hashlib.sha256(exact_message.encode()).hexdigest(),
        "exact_message": exact_message,
    }
    return result


def canonical_tasks():
    tasks = []
    for path in sorted(CONFIG_DIR.glob("*.raw.json")):
        data = json.loads(path.read_text())
        for position, task in enumerate(data, 1):
            if "mattermost" not in task.get("sites", []):
                continue
            tasks.append(
                {
                    "scope": "canonical",
                    "task_key": task["task_id"],
                    "source_config": path.name,
                    "source_position": position,
                    "mattermost_position": (
                        position if path.name == "mattermost.raw.json" else ""
                    ),
                    "sites": ",".join(task["sites"]),
                    "intent": task["intent"],
                    "hint": task.get("eval", {})
                    .get("reference_answers", {})
                    .get("hint", ""),
                }
            )
    return sorted(tasks, key=lambda task: task["task_key"])


def legacy_tasks():
    tasks = []
    for path in sorted((MATTERMOST_DIR / "tasks").glob("*.json"), key=lambda p: int(p.stem)):
        task = json.loads(path.read_text())
        tasks.append(
            {
                "scope": "legacy",
                "task_key": path.name,
                "source_config": f"tasks/{path.name}",
                "source_position": int(path.stem),
                "mattermost_position": "",
                "sites": "mattermost",
                "intent": task["intent"],
                "hint": task.get("eval", {}).get("string_note", ""),
            }
        )
    return tasks


def task_evidence_ids(task: dict):
    if task["scope"] == "legacy":
        return LEGACY_EVIDENCE[task["task_key"]]
    return TASK_EVIDENCE.get(task["task_key"], ())


def state_note(task: dict) -> str:
    if task["scope"] == "legacy":
        return "Legacy read-only task; exact supporting post(s) are protected below."
    return STATE_NOTES.get(
        task["task_key"],
        "Exact supporting post(s) are protected below; other required values come from the listed external sites.",
    )


def csv_rows(tasks: list[dict], evidence: dict[str, dict]):
    for task in tasks:
        evidence_ids = task_evidence_ids(task)
        if not evidence_ids:
            yield {
                **task,
                "evidence_id": "STATE",
                "post_id": "",
                "team": "",
                "channel": "",
                "author": "",
                "create_at_ms": "",
                "original_newest_rank": "",
                "original_synthetic": "",
                "sha256": "",
                "exact_message": "",
                "state_or_destination_note": state_note(task),
            }
            continue
        for evidence_id in evidence_ids:
            yield {
                **task,
                **evidence[evidence_id],
                "state_or_destination_note": state_note(task),
            }


def markdown_escape(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def write_markdown(path: Path, tasks: list[dict], evidence: dict[str, dict]):
    lines = [
        "# Mattermost task message evidence",
        "",
        "This is the durable index for all 38 canonical tasks whose `sites` include "
        "Mattermost, plus the 10 legacy Mattermost read-only tasks. The adjacent "
        "`task_message_evidence.csv` is the canonical exact table: it includes the "
        "full intent, current hint, one row per evidence message, exact multiline "
        "message text, stable post ID or marker, timestamp, original rank, and SHA-256.",
        "",
        "The protected original messages E01-E18 must not be deleted or retimestamped. "
        "Dataset backfill is assigned older source timestamps, so every protected "
        "message stays within the newest 100 posts and retains its original newest-first rank. "
        "E19 is a dataset-derived fixed DM used to make Emma Davis the unambiguous recent "
        "Mattermost interaction for the cross-site tasks.",
        "",
        "## Task index",
        "",
        "| Scope | Source position | Mattermost position | Task ID/file | Sites | Evidence | Intent |",
        "|---|---:|---:|---|---|---|---|",
    ]
    for task in tasks:
        evidence_ids = task_evidence_ids(task)
        lines.append(
            "| "
            + " | ".join(
                markdown_escape(value)
                for value in (
                    task["scope"],
                    task["source_position"],
                    task["mattermost_position"],
                    task["task_key"],
                    task["sites"],
                    ", ".join(evidence_ids) if evidence_ids else "STATE",
                    task["intent"],
                )
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Exact protected-message catalog",
            "",
            "| Evidence | Post ID / stable marker | Location | Author | CreateAt (ms) | Original newest rank | Original synthetic | SHA-256 | Exact message |",
            "|---|---|---|---|---:|---:|---|---|---|",
        ]
    )
    for evidence_id in sorted(evidence, key=lambda value: int(value[1:])):
        item = evidence[evidence_id]
        lines.append(
            "| "
            + " | ".join(
                markdown_escape(value)
                for value in (
                    evidence_id,
                    item["post_id"],
                    "/".join(filter(None, (item["team"], item["channel"]))),
                    item["author"],
                    item["create_at_ms"],
                    item["original_newest_rank"],
                    item["original_synthetic"],
                    item["sha256"],
                    item["exact_message"],
                )
            )
            + " |"
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> int:
    seed = json.loads((MATTERMOST_DIR / "seed_data.json").read_text())
    backfill = json.loads(
        (MATTERMOST_DIR / "existing_channel_backfill_seed.json").read_text()
    )
    evidence = protected_evidence(seed, backfill)
    tasks = canonical_tasks() + legacy_tasks()
    if sum(task["scope"] == "canonical" for task in tasks) != 38:
        raise RuntimeError("Expected exactly 38 canonical Mattermost tasks")

    fields = [
        "scope", "task_key", "source_config", "source_position",
        "mattermost_position", "sites", "intent", "hint", "evidence_id",
        "post_id", "team", "channel", "author", "create_at_ms",
        "original_newest_rank", "original_synthetic", "sha256", "exact_message",
        "state_or_destination_note",
    ]
    output_csv = MATTERMOST_DIR / "task_message_evidence.csv"
    with output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(csv_rows(tasks, evidence))

    output_json = MATTERMOST_DIR / "protected_task_messages.json"
    output_json.write_text(json.dumps(list(evidence.values()), indent=2) + "\n")
    output_md = MATTERMOST_DIR / "TASK_MESSAGE_EVIDENCE.md"
    write_markdown(output_md, tasks, evidence)
    print(
        f"Wrote {output_csv.name}, {output_json.name}, and {output_md.name}: "
        f"{len(tasks)} tasks, {len(evidence)} evidence messages"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python
"""Replay saved trajectories through RubricVerifier and capture LLM I/O.

Drives the RubricVerifier directly against pre-recorded trajectory artifacts
(step_*.pkl.gz + screenshot_step_*.png) under a study dir from
`drive-download-20260424T050525Z-3-001/...`. No Docker, no env, no real
agent — every (action, before-screenshot, after-screenshot) tuple from the
saved run is fed to the verifier as if it were happening live.

Output layout (default `--output <study-dir>/_replay`):

    <output>/<task_id>/
    ├── llm_calls/
    │   ├── 000.json   (exact OpenAI request kwargs + response.model_dump())
    │   ├── 001.json
    │   └── ...
    └── eval_results.json   (RubricVerifier writes this on the final step)

Usage:
    uv run scripts/replay_verifier_on_drive.py                  # task 302 only
    uv run scripts/replay_verifier_on_drive.py --tasks all
    uv run scripts/replay_verifier_on_drive.py --tasks 300,303
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import pickle
import re
import sys
import time
from pathlib import Path

import numpy as np
from openai import OpenAI
from PIL import Image

from webarena_pro_bgym.step_verifier import scale_bbox_to_screenshot
from webarena_pro_core.verifier.model_config import GEMINI_BASE_URL
from webarena_pro_core.verifier.rubric_verifier import RubricVerifier
from webarena_pro_core.verifier.types import _extract_first_string_arg


DEFAULT_STUDY_DIR = (
    "/home/weijian/webarena-pro/drive-download-20260424T050525Z-3-001/"
    "2026-04-23_12-18-28_genericagent-gemini-3-1-pro-preview-on-webarena-pro-"
    "metabase-300-301-302-303-304-305-306-307-308-309"
)
DEFAULT_ENV_PATH = Path("/home/weijian/webarena-pro/webarena-pro-bgym/.env")


# ---------------------------------------------------------------------------
# Per-task rubrics. The intent text comes from
# webarena-pro-core/src/webarena_pro_core/config/{metabase,mattermost}.raw.json.
# These are deliberately short — refine per-task as needed.
# ---------------------------------------------------------------------------

def _qa_rubrics(intent_summary: str) -> list[str]:
    """Generic 'find an answer in messages' rubric pair."""
    return [
        f"The agent located the information needed to answer: {intent_summary}",
        "The agent reported a complete and correct answer via send_msg_to_user",
    ]


RUBRICS_BY_TASK_ID: dict[int, list[str]] = {
    # --- mattermost 200-208 (Q&A over channel messages) -------------------
    200: _qa_rubrics("Who is the onboarding buddy assigned to Mike Ross?"),
    201: _qa_rubrics(
        "What service is scheduled for deployment on Tuesday in the "
        "March 10-14 weekly deployment schedule, and who is the owner?"
    ),
    202: _qa_rubrics(
        "How many test cases passed and how many failed in the Sprint 11 "
        "QA report for Project Alpha?"
    ),
    203: _qa_rubrics(
        "What tech stack was proposed for Project Beta and who proposed it?"
    ),
    204: _qa_rubrics(
        "Q1 marketing campaign results: by how much did website traffic exceed "
        "the target, and what was the cost per acquisition vs target?"
    ),
    205: _qa_rubrics(
        "March 8 security incident in security-alerts: severity, attack type, "
        "and Lisa Wang's recommendation"
    ),
    206: _qa_rubrics(
        "March 10 Infrastructure Status in devops: production uptime, p99 "
        "latency spike cause, and how it was handled"
    ),
    207: _qa_rubrics(
        "Henry Taylor's events post: company events between March 20 and "
        "March 31, with date and time for each"
    ),
    208: _qa_rubrics(
        "Weekly marketing analytics for March 3-9: demo page conversion rate "
        "(demo requests / demo page views), and how it compares"
    ),
    # --- metabase 300-309 (action / state goals) --------------------------
    300: [
        "The agent navigated to the order-items data view in Metabase",
        "The agent identified the order item with the lowest discount",
        "The agent reported the order ID as the answer via send_msg_to_user",
    ],
    301: [
        "The agent applied a date filter restricting orders to the last 7 days",
        "The agent saved the resulting question with name 'Recent Orders - Last 7 Days'",
    ],
    302: [
        "The agent navigated to the 'My Analytics' / personal collection",
        "The agent created a new timeline event under that collection",
        "The event is named 'test' and scheduled exactly one week from today",
    ],
    303: [
        "The agent filtered products by the vendor 'Legros-Gleason'",
        "The agent reported the count of matching products via send_msg_to_user",
    ],
    304: [
        "The summary aggregation is count of order items grouped by unit price",
        "The visualization is set to bar chart",
        "The question is saved as 'Order Items by Unit Price'",
    ],
    305: [
        "A dashboard 'Operations KPI Pack' was created in the 'Our Analytics' folder",
        "The dashboard contains the query-builder question 'Order Count by Status - Builder'",
        "The dashboard contains the SQL question 'Top 10 Products by Revenue - SQL'",
    ],
    306: [
        "The 'E-commerce Insights' dashboard date filter is set to the previous 7 days",
        "The dashboard was exported as a PDF file",
    ],
    307: [
        "A new dashboard 'Sales Overview Dashboard 2' was created under 'Our Analytics'",
        "The dashboard contains a title text element saying 'Sales Overview Dashboard 2'",
        "The dashboard contains the 'Orders' card / question",
    ],
    308: [
        "A new text section was added to the 'AgentLab Documentation' dashboard",
        "The section heading is 'Key Python Implementations'",
        "The section content documents Python function implementations for AgentLab",
    ],
    309: [
        "The visualization of 'Orders by Status' was changed to a bar chart",
        "The change was saved",
    ],
}


# ---------------------------------------------------------------------------
# Recording OpenAI client wrapper. Captures every chat.completions.create call
# verbatim (request kwargs + response.model_dump()).
# ---------------------------------------------------------------------------

class _LoggedCompletions:
    def __init__(self, parent: "RecordingClient") -> None:
        self._parent = parent

    def create(self, **kwargs):
        resp = self._parent._inner.chat.completions.create(**kwargs)
        try:
            resp_dict = resp.model_dump()
        except Exception:
            resp_dict = {"_repr": repr(resp)}
        self._parent.calls.append({"request": kwargs, "response": resp_dict})
        return resp


class _LoggedChat:
    def __init__(self, parent: "RecordingClient") -> None:
        self.completions = _LoggedCompletions(parent)


class RecordingClient:
    """Stand-in for `openai.OpenAI` that records every completions call."""

    def __init__(self, inner: OpenAI) -> None:
        self._inner = inner
        self.calls: list[dict] = []
        self.chat = _LoggedChat(self)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TASK_ID_RE = re.compile(r"on_webarena-pro-bgym\.(\d+)_\d+$")
# Study dirs are named like `2026-04-23_12-18-28_genericagent-...`
_STUDY_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_(\d{2})-(\d{2})-(\d{2})_")


def _parse_recording_unix(study_dir: Path) -> float | None:
    """Parse the leading `YYYY-MM-DD_HH-MM-SS_` prefix → unix epoch (UTC).
    Returns None if the dir name doesn't start with a recognised timestamp."""
    m = _STUDY_DATE_RE.match(study_dir.name)
    if not m:
        return None
    from datetime import datetime, timezone
    y, mo, d, h, mi, s = (int(g) for g in m.groups())
    return datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc).timestamp()


def _load_env(path: Path) -> None:
    """Tiny .env loader to avoid an extra dep."""
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if "=" not in s:
            continue
        k, _, v = s.partition("=")
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        if k and v and k not in os.environ:
            os.environ[k] = v


def _load_step(path: Path):
    with gzip.open(path, "rb") as f:
        return pickle.load(f)


def _agent_think(agent_info) -> str | None:
    if agent_info is None:
        return None
    if isinstance(agent_info, dict):
        return agent_info.get("think")
    return getattr(agent_info, "think", None)


def _extract_bid_and_bbox(action: str | None, pre_obs: dict):
    if not action:
        return None, None
    bid = _extract_first_string_arg(action)
    extras = pre_obs.get("extra_element_properties") or {}
    if bid is None or bid not in extras:
        return None, None
    raw_bbox = extras[bid].get("bbox")
    if raw_bbox is None:
        return bid, None
    return bid, tuple(raw_bbox)


def _build_record(
    *,
    task_name: str,
    exp_dir: Path,
    step_idx: int,
    action: str,
    pre_obs: dict,
    screenshot_before: np.ndarray,
    screenshot_after: np.ndarray,
    agent_think: str | None,
    is_final: bool,
    timestamp: float,
) -> dict:
    bid, bbox = _extract_bid_and_bbox(action, pre_obs)
    # Saved PNGs are at 1× DPR but DOM extras are at the live DPR (often
    # 2×). Reconcile so the bbox lands on the actual element pixels.
    bbox = scale_bbox_to_screenshot(
        bbox, pre_obs.get("extra_element_properties"), screenshot_before
    )
    return {
        "step": step_idx,
        "task_name": task_name,
        "exp_dir": str(exp_dir),
        "goal": pre_obs.get("goal"),
        "url": pre_obs.get("url"),
        "action": action,
        "bid": bid,
        "bbox": bbox,
        "screenshot_before": screenshot_before,
        "screenshot_after": screenshot_after,
        "agent_think": agent_think,
        "is_final_step": is_final,
        "timestamp": timestamp,
    }


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------

def replay_one_task(
    task_dir: Path,
    output_root: Path,
    model_name: str,
    *,
    max_steps: int | None = None,
    recording_unix: float | None = None,
) -> bool:
    m = _TASK_ID_RE.search(task_dir.name)
    if not m:
        print(f"  skip: cannot parse task id from {task_dir.name}", file=sys.stderr)
        return False
    task_id = int(m.group(1))
    rubrics = RUBRICS_BY_TASK_ID.get(task_id)
    if rubrics is None:
        print(f"  skip task {task_id}: no rubric defined")
        return False

    out_task_dir = output_root / str(task_id)
    out_task_dir.mkdir(parents=True, exist_ok=True)
    llm_calls_dir = out_task_dir / "llm_calls"
    llm_calls_dir.mkdir(exist_ok=True)

    step_files = sorted(
        task_dir.glob("step_*.pkl.gz"),
        key=lambda p: int(p.stem.split("_")[1].split(".")[0]),
    )
    if len(step_files) < 2:
        print(f"  skip task {task_id}: <2 step files in {task_dir}")
        return False
    steps = [_load_step(p) for p in step_files]

    # Screenshots live next to step pickles as PNGs (pickled obs has no
    # 'screenshot' key — it was extracted to disk during the original run).
    screenshots: dict[int, np.ndarray] = {}
    for png in task_dir.glob("screenshot_step_*.png"):
        idx = int(png.stem.split("_")[2])
        screenshots[idx] = np.asarray(Image.open(png).convert("RGB"))

    rec_client = RecordingClient(
        OpenAI(api_key=os.environ["GEMINI_API_KEY"], base_url=GEMINI_BASE_URL)
    )
    verifier = RubricVerifier(
        rubric_descriptions=rubrics,
        openai_client=rec_client,
        model_name=model_name,
    )
    task_name = f"webarena-pro-bgym.{task_id}"

    # Replay: dispatch (steps[i], steps[i].action, steps[i+1]) for i in 0..N-1.
    # Mirrors the agent loop in study.py — None action means the loop broke
    # before from_step, so no record was emitted then either.
    n_transitions = len(steps) - 1
    if max_steps is not None:
        n_transitions = min(n_transitions, max_steps)

    n_dispatched = 0
    for i in range(n_transitions):
        pre = steps[i]
        post = steps[i + 1]
        action = getattr(pre, "action", None)
        if action is None:
            continue
        if i not in screenshots or (i + 1) not in screenshots:
            print(f"  task {task_id} step {i}: missing screenshot, skipping")
            continue
        is_final = bool(
            getattr(post, "terminated", False)
            or getattr(post, "truncated", False)
        ) and (i == n_transitions - 1)
        # Anchor the judge's "today" against the original recording, plus a
        # small per-step offset so steps still order correctly in time.
        ts = (recording_unix + i) if recording_unix is not None else time.time()
        record = _build_record(
            task_name=task_name,
            exp_dir=out_task_dir,
            step_idx=getattr(post, "step", i + 1),
            action=action,
            pre_obs=getattr(pre, "obs", None) or {},
            screenshot_before=screenshots[i],
            screenshot_after=screenshots[i + 1],
            agent_think=_agent_think(getattr(pre, "agent_info", None)),
            is_final=is_final,
            timestamp=ts,
        )
        try:
            verifier.on_agent_step_end(record)
        except Exception as e:
            print(f"  task {task_id} step {i}: verifier raised: {type(e).__name__}: {e}")
            return False
        n_dispatched += 1

    # Dump LLM I/O.
    for idx, entry in enumerate(rec_client.calls):
        (llm_calls_dir / f"{idx:03d}.json").write_text(
            json.dumps(entry, indent=2, default=str)
        )

    final = verifier.final_verdict()  # cheap; reset already happened on final step
    print(
        f"  task {task_id}: dispatched {n_dispatched} step(s), "
        f"{len(rec_client.calls)} LLM call(s) saved to {llm_calls_dir}, "
        f"in-memory final={final} (authoritative is {out_task_dir / 'eval_results.json'})"
    )
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--study-dir", default=DEFAULT_STUDY_DIR)
    parser.add_argument(
        "--tasks",
        default="302",
        help="Comma-separated task ids, or 'all' (default: 302).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output root (default: <study-dir>/_replay).",
    )
    parser.add_argument("--model", default="gemini-3-flash-preview")
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Cap number of transitions per task (cost guard).",
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_PATH),
        help="Path to .env to load GEMINI_API_KEY from.",
    )
    args = parser.parse_args()

    _load_env(Path(args.env_file))
    if "GEMINI_API_KEY" not in os.environ:
        sys.exit(f"GEMINI_API_KEY not set (and not found in {args.env_file})")

    study_dir = Path(args.study_dir)
    if not study_dir.is_dir():
        sys.exit(f"Study dir does not exist: {study_dir}")
    output_root = Path(args.output) if args.output else study_dir / "_replay"
    output_root.mkdir(parents=True, exist_ok=True)

    wanted: set[int] | None
    if args.tasks.strip().lower() == "all":
        wanted = None
    else:
        wanted = {int(s) for s in args.tasks.split(",") if s.strip()}

    task_dirs = sorted(
        d for d in study_dir.iterdir() if d.is_dir() and _TASK_ID_RE.search(d.name)
    )
    recording_unix = _parse_recording_unix(study_dir)
    if recording_unix is None:
        print(
            f"warn: could not parse recording date from study dir name "
            f"{study_dir.name!r}; judges will fall back to wall-clock 'now' for "
            f"'today' resolution.",
            file=sys.stderr,
        )
    else:
        from datetime import datetime, timezone
        iso = datetime.fromtimestamp(recording_unix, tz=timezone.utc).isoformat()
        print(f"recording date: {iso}")

    n_replayed = 0
    for td in task_dirs:
        m = _TASK_ID_RE.search(td.name)
        tid = int(m.group(1))
        if wanted is not None and tid not in wanted:
            continue
        print(f"replaying {td.name}...")
        if replay_one_task(
            td,
            output_root,
            args.model,
            max_steps=args.max_steps,
            recording_unix=recording_unix,
        ):
            n_replayed += 1

    print(f"\nDone. Replayed {n_replayed} task(s). Output: {output_root}")


if __name__ == "__main__":
    main()

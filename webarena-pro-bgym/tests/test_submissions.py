import gzip
import json
import pickle
from pathlib import Path
from types import SimpleNamespace

from webarena_pro_bgym.submissions import (
    collect_submission_tasks,
    merge_submission_tasks,
    write_combined_raw_json,
)


def _write_submission_json(path: Path, task: dict, **overrides) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "start_site": task["sites"][0],
        "task_id": task["task_id"],
        "created_at": "2026-04-30T12:56:40+00:00",
        "queue_status": "finished",
        "status": "failed",
        "return_code": 1,
        "task": task,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_review_json(path: Path, **overrides) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "reviewer": "reviewer@example.com",
        "reviewer_source": "cloudflare_access",
        "reviewed_at": "2026-05-05T12:00:00Z",
        "task_intent": "Reviewed task intent",
        "rubrics": [
            {"type": "action", "text": "Reviewed action rubric"},
            {"type": "outcome", "text": "Reviewed outcome rubric"},
        ],
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _write_eval_results(source_dir: Path, task_id: int | str, final_verdict: str) -> None:
    path = source_dir / f"run_on_webarena-pro-bgym.{task_id}_0" / "eval_results.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"final_verdict": final_verdict}), encoding="utf-8")


def test_collect_submission_tasks_reads_failed_submission_json(tmp_path):
    root = tmp_path / "agentlab_results"
    submission_dir = root / "2026-04-30_12-56-40_jobportal-submission-123"
    task = {
        "sites": ["jobportal"],
        "task_id": 123,
        "intent": "How many jobs did Helix AI post?",
        "require_login": True,
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    _write_submission_json(submission_dir / "submission.json", task)

    collected = collect_submission_tasks(root, failed_only=True)

    assert len(collected) == 1
    assert collected[0].site == "jobportal"
    assert collected[0].task_id == "123"
    assert collected[0].submission_status == "failed"
    assert collected[0].task["_submission"]["status"] == "failed"
    assert collected[0].task["_submission"]["return_code"] == 1


def test_collect_submission_tasks_can_filter_reviewed_verifier_failures(tmp_path):
    root = tmp_path / "agentlab_results"

    cases = [
        (1, "Reviewed failed task", "fail", True),
        (2, "Reviewed passed task", "pass", True),
        (3, "Unreviewed failed task", "fail", False),
    ]
    for task_id, intent, verdict, reviewed in cases:
        submission_dir = root / f"2026-04-30_12-56-4{task_id}_jobportal-submission-{task_id}"
        task = {
            "sites": ["jobportal"],
            "task_id": task_id,
            "intent": intent,
            "eval": {"eval_types": ["rubric_verifier"]},
        }
        _write_submission_json(
            submission_dir / "submission.json",
            task,
            status="succeeded",
            return_code=0,
        )
        _write_eval_results(submission_dir, task_id, verdict)
        if reviewed:
            _write_review_json(
                root / ".task_reviews" / submission_dir.name / "reviewer_example.com.json",
                task_intent=intent,
            )

    collected = collect_submission_tasks(
        root,
        reviewed_only=True,
        verifier_failed_only=True,
    )

    assert [task.task_id for task in collected] == ["1"]
    assert collected[0].task["_submission"]["reviewed"] is True
    assert collected[0].task["_submission"]["verifier_verdict"] == "fail"


def test_collect_submission_tasks_applies_review_overlay_and_marks_submission(tmp_path):
    root = tmp_path / "agentlab_results"
    submission_dir = root / "2026-04-30_12-56-40_jobportal-submission-123"
    task = {
        "sites": ["jobportal"],
        "task_id": 123,
        "intent": "Original task intent",
        "require_login": True,
        "eval": {
            "eval_types": ["rubric_verifier"],
            "rubrics": [{"type": "action", "text": "Original rubric"}],
        },
    }
    _write_submission_json(submission_dir / "submission.json", task)
    _write_review_json(
        root
        / ".task_reviews"
        / submission_dir.name
        / "reviewer_example.com.json",
    )

    collected = collect_submission_tasks(root)

    assert len(collected) == 1
    collected_task = collected[0].task
    assert collected_task["intent"] == "Reviewed task intent"
    assert collected_task["eval"]["rubrics"] == [
        {"type": "action", "text": "Reviewed action rubric"},
        {"type": "outcome", "text": "Reviewed outcome rubric"},
    ]
    assert collected_task["_submission"]["reviewed"] is True
    assert collected_task["_submission"]["reviewed_by"] == "reviewer@example.com"

    submission = json.loads((submission_dir / "submission.json").read_text(encoding="utf-8"))
    assert submission["reviewed"] is True
    assert submission["reviewed_by"] == "reviewer@example.com"
    assert submission["reviewed_at"] == "2026-05-05T12:00:00Z"
    assert submission["task"]["intent"] == "Reviewed task intent"
    assert submission["task"]["eval"]["rubrics"] == [
        {"type": "action", "text": "Reviewed action rubric"},
        {"type": "outcome", "text": "Reviewed outcome rubric"},
    ]


def test_collect_submission_tasks_can_avoid_writing_review_tags(tmp_path):
    root = tmp_path / "agentlab_results"
    submission_dir = root / "2026-04-30_12-56-40_jobportal-submission-123"
    task = {
        "sites": ["jobportal"],
        "task_id": 123,
        "intent": "Original task intent",
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    _write_submission_json(submission_dir / "submission.json", task)
    _write_review_json(
        root
        / ".task_reviews"
        / submission_dir.name
        / "reviewer_example.com.json",
    )

    collected = collect_submission_tasks(root, mark_reviewed_submissions=False)

    assert collected[0].task["intent"] == "Reviewed task intent"
    submission = json.loads((submission_dir / "submission.json").read_text(encoding="utf-8"))
    assert "reviewed" not in submission
    assert submission["task"]["intent"] == "Original task intent"


def test_collect_submission_tasks_normalizes_scientific_task_id_from_source_dir(tmp_path):
    root = tmp_path / "agentlab_results"
    exact_task_id = "20260502150439052116"
    submission_dir = root / f"2026-05-02_15-04-39_immich-submission-{exact_task_id}"
    task = {
        "sites": ["immich"],
        "task_id": 2.026050215043905e19,
        "intent": "Task with lossy id",
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    _write_submission_json(
        submission_dir / "submission.json",
        task,
        task_id=2.026050215043905e19,
    )

    collected = collect_submission_tasks(root)

    assert collected[0].task_id == exact_task_id
    assert collected[0].task["task_id"] == exact_task_id
    submission = json.loads((submission_dir / "submission.json").read_text(encoding="utf-8"))
    assert submission["task_id"] == exact_task_id
    assert submission["task"]["task_id"] == exact_task_id


def test_collect_submission_tasks_ignores_archived_submission_json(tmp_path):
    root = tmp_path / "agentlab_results"
    active_dir = root / "2026-04-30_12-56-40_jobportal-submission-123"
    archived_dir = root / "2026-05-01_12-56-40_jobportal-submission-123"
    active_task = {
        "sites": ["jobportal"],
        "task_id": 123,
        "intent": "Active task",
        "require_login": True,
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    archived_task = {
        "sites": ["jobportal"],
        "task_id": 123,
        "intent": "Archived task",
        "require_login": True,
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    _write_submission_json(active_dir / "submission.json", active_task, archived=False)
    _write_submission_json(archived_dir / "submission.json", archived_task, archived=True)

    collected = collect_submission_tasks(root)

    assert len(collected) == 1
    assert collected[0].task["intent"] == "Active task"


def test_collect_submission_tasks_ignores_review_excluded_submissions(tmp_path):
    root = tmp_path / "agentlab_results"
    active_dir = root / "2026-04-30_12-56-40_jobportal-submission-1"
    infeasible_dir = root / "2026-04-30_12-57-40_jobportal-submission-2"
    ambiguous_dir = root / "2026-04-30_12-58-40_jobportal-submission-3"
    active_task = {
        "sites": ["jobportal"],
        "task_id": 1,
        "intent": "Active task",
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    infeasible_task = {
        "sites": ["jobportal"],
        "task_id": 2,
        "intent": "Infeasible task",
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    ambiguous_task = {
        "sites": ["jobportal"],
        "task_id": 3,
        "intent": "Ambiguous task",
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    _write_submission_json(active_dir / "submission.json", active_task)
    _write_submission_json(infeasible_dir / "submission.json", infeasible_task)
    _write_submission_json(ambiguous_dir / "submission.json", ambiguous_task)
    _write_review_json(
        root / ".task_reviews" / infeasible_dir.name / "reviewer_example.com.json",
        feasibility={"rating": "infeasible", "note": "Missing required data"},
        ambiguity={"rating": "clear", "note": ""},
    )
    _write_review_json(
        root / ".task_reviews" / ambiguous_dir.name / "reviewer_example.com.json",
        feasibility={"rating": "feasible", "note": ""},
        ambiguity={"rating": "ambiguous", "note": "Target is underspecified"},
    )

    collected = collect_submission_tasks(root)

    assert [task.task_id for task in collected] == ["1"]


def test_collect_submission_tasks_deduplicates_intent_and_keeps_latest_run(tmp_path):
    root = tmp_path / "agentlab_results"
    older_dir = root / "2026-04-30_12-56-40_jobportal-submission-1"
    latest_dir = root / "2026-04-30_12-57-40_jobportal-submission-2"
    older_task = {
        "sites": ["jobportal"],
        "task_id": 1,
        "intent": "Find duplicate task",
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    latest_task = {
        "sites": ["jobportal"],
        "task_id": 2,
        "intent": "Find duplicate   task",
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    _write_submission_json(
        older_dir / "submission.json",
        older_task,
        created_at="2026-04-30T12:56:40+00:00",
        finished_at="2026-04-30T12:58:40+00:00",
    )
    _write_submission_json(
        latest_dir / "submission.json",
        latest_task,
        created_at="2026-04-30T12:57:40+00:00",
        finished_at="2026-04-30T12:59:40+00:00",
    )

    collected = collect_submission_tasks(root)

    assert [task.task_id for task in collected] == ["2"]


def test_collect_submission_tasks_recovers_older_submission_from_study_pickle(tmp_path):
    root = tmp_path / "agentlab_results"
    submission_dir = root / "2026-04-24_20-09-15_mattermost-submission-209"
    exp_dir = submission_dir / "2026-04-24_GenericAgent_on_webarena-pro-bgym.209_0"
    exp_dir.mkdir(parents=True)
    (exp_dir / "summary_info.json").write_text(
        json.dumps({"cum_reward": 0.0, "n_steps": 30}),
        encoding="utf-8",
    )
    raw_task = {
        "sites": ["mattermost"],
        "task_id": 209,
        "intent": "Who are the new hires?",
        "require_login": True,
        "eval": {"eval_types": ["llm_judge_with_hint"]},
    }
    study = SimpleNamespace(
        exp_args_list=[
            SimpleNamespace(
                env_args=SimpleNamespace(
                    task_config=SimpleNamespace(raw_task=raw_task),
                )
            )
        ]
    )
    with gzip.open(submission_dir / "study.pkl.gz", "wb") as handle:
        pickle.dump(study, handle)

    collected = collect_submission_tasks(root, failed_only=True)

    assert len(collected) == 1
    assert collected[0].site == "mattermost"
    assert collected[0].task_id == "209"
    assert collected[0].run_status == "failed"
    assert collected[0].reward == 0.0
    assert collected[0].task["_submission"]["source_kind"] == "study.pkl.gz"
    assert collected[0].task["_submission"]["run_status"] == "failed"


def test_merge_submission_tasks_adds_without_duplicating_existing_task(tmp_path):
    root = tmp_path / "agentlab_results"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "jobportal.raw.json").write_text(
        json.dumps(
            [
                {
                    "sites": ["jobportal"],
                    "task_id": 1,
                    "intent": "Existing task",
                }
            ]
        ),
        encoding="utf-8",
    )
    task = {
        "sites": ["jobportal"],
        "task_id": 2,
        "intent": "New submitted task",
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    _write_submission_json(root / "jobportal-submission-2" / "submission.json", task)

    stats = merge_submission_tasks(collect_submission_tasks(root), config_dir)

    assert stats.added == 1
    assert stats.skipped_existing == 0
    raw_tasks = json.loads((config_dir / "jobportal.raw.json").read_text(encoding="utf-8"))
    assert [task["task_id"] for task in raw_tasks] == [1, 2]

    stats = merge_submission_tasks(collect_submission_tasks(root), config_dir)

    assert stats.added == 0
    assert stats.skipped_existing == 1


def test_merge_submission_tasks_removes_existing_archived_submission(tmp_path):
    root = tmp_path / "agentlab_results"
    config_dir = tmp_path / "config"
    archived_dir = root / "2026-05-01_12-56-40_jobportal-submission-123"
    archived_task = {
        "sites": ["jobportal"],
        "task_id": 123,
        "intent": "Archived task",
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    _write_submission_json(archived_dir / "submission.json", archived_task, archived=True)
    config_dir.mkdir()
    (config_dir / "jobportal.raw.json").write_text(
        json.dumps(
            [
                {
                    "sites": ["jobportal"],
                    "task_id": 1,
                    "intent": "Existing task",
                },
                {
                    **archived_task,
                    "_submission": {"source_dir": str(archived_dir)},
                },
            ]
        ),
        encoding="utf-8",
    )

    stats = merge_submission_tasks([], config_dir)

    assert stats.removed_archived == 1
    raw_tasks = json.loads((config_dir / "jobportal.raw.json").read_text(encoding="utf-8"))
    assert [task["task_id"] for task in raw_tasks] == [1]


def test_merge_submission_tasks_removes_existing_review_excluded_submission(tmp_path):
    root = tmp_path / "agentlab_results"
    config_dir = tmp_path / "config"
    excluded_dir = root / "2026-05-01_12-56-40_jobportal-submission-123"
    excluded_task = {
        "sites": ["jobportal"],
        "task_id": 123,
        "intent": "Review-excluded task",
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    _write_review_json(
        root / ".task_reviews" / excluded_dir.name / "reviewer_example.com.json",
        feasibility={"rating": "feasible", "note": ""},
        ambiguity={"rating": "ambiguous", "note": "Target is underspecified"},
    )
    config_dir.mkdir()
    (config_dir / "jobportal.raw.json").write_text(
        json.dumps(
            [
                {
                    "sites": ["jobportal"],
                    "task_id": 1,
                    "intent": "Existing task",
                },
                {
                    **excluded_task,
                    "_submission": {"source_dir": str(excluded_dir)},
                },
            ]
        ),
        encoding="utf-8",
    )

    stats = merge_submission_tasks([], config_dir)

    assert stats.removed_review_excluded == 1
    raw_tasks = json.loads((config_dir / "jobportal.raw.json").read_text(encoding="utf-8"))
    assert [task["task_id"] for task in raw_tasks] == [1]


def test_merge_submission_tasks_can_keep_only_collected_submission_tasks(tmp_path):
    root = tmp_path / "agentlab_results"
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    submission_dir = root / "2026-04-30_12-56-40_jobportal-submission-1"
    task = {
        "sites": ["jobportal"],
        "task_id": 1,
        "intent": "Reviewed failed task",
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    _write_submission_json(
        submission_dir / "submission.json",
        task,
        status="succeeded",
        return_code=0,
    )
    _write_eval_results(submission_dir, 1, "fail")
    _write_review_json(
        root / ".task_reviews" / submission_dir.name / "reviewer_example.com.json",
        task_intent="Reviewed failed task",
    )
    (config_dir / "jobportal.raw.json").write_text(
        json.dumps(
            [
                {
                    "sites": ["jobportal"],
                    "task_id": "base",
                    "intent": "Base task",
                },
                {
                    "sites": ["jobportal"],
                    "task_id": 1,
                    "intent": "Stale collected task",
                    "_submission": {
                        "source": "agentlab_submission",
                        "source_dir": str(submission_dir),
                    },
                },
                {
                    "sites": ["jobportal"],
                    "task_id": 2,
                    "intent": "Uncollected submission task",
                    "_submission": {
                        "source": "agentlab_submission",
                        "source_dir": str(root / "jobportal-submission-2"),
                    },
                },
            ]
        ),
        encoding="utf-8",
    )

    stats = merge_submission_tasks(
        collect_submission_tasks(
            root,
            reviewed_only=True,
            verifier_failed_only=True,
        ),
        config_dir,
        replace_existing=True,
        keep_only_collected=True,
    )

    assert stats.removed_uncollected == 1
    assert stats.replaced == 1
    raw_tasks = json.loads((config_dir / "jobportal.raw.json").read_text(encoding="utf-8"))
    assert [task["task_id"] for task in raw_tasks] == ["base", 1]
    assert raw_tasks[1]["intent"] == "Reviewed failed task"


def test_merge_submission_tasks_removes_duplicate_intents_and_keeps_latest_run(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "jobportal.raw.json").write_text(
        json.dumps(
            [
                {
                    "sites": ["jobportal"],
                    "task_id": 1,
                    "intent": "Find duplicate task",
                    "_submission": {
                        "finished_at": "2026-04-30T12:58:40+00:00",
                    },
                },
                {
                    "sites": ["jobportal"],
                    "task_id": 2,
                    "intent": "Find duplicate   task",
                    "_submission": {
                        "finished_at": "2026-04-30T12:59:40+00:00",
                    },
                },
            ]
        ),
        encoding="utf-8",
    )

    stats = merge_submission_tasks([], config_dir)

    assert stats.removed_duplicates == 1
    raw_tasks = json.loads((config_dir / "jobportal.raw.json").read_text(encoding="utf-8"))
    assert [task["task_id"] for task in raw_tasks] == [2]


def test_collect_submission_tasks_falls_back_to_plain_exp_args_pickle(tmp_path):
    root = tmp_path / "agentlab_results"
    submission_dir = root / "2026-04-30_12-56-40_jobportal-submission-123"
    exp_dir = submission_dir / "2026-04-30_GenericAgent_on_webarena-pro-bgym.123_0"
    exp_dir.mkdir(parents=True)
    raw_task = {
        "sites": ["jobportal"],
        "task_id": 123,
        "intent": "Fallback task",
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    exp_args = SimpleNamespace(
        env_args=SimpleNamespace(
            task_config=SimpleNamespace(raw_task=raw_task),
        )
    )
    with (exp_dir / "exp_args.pkl").open("wb") as handle:
        pickle.dump(exp_args, handle)

    collected = collect_submission_tasks(root)

    assert len(collected) == 1
    assert collected[0].task_id == "123"
    assert collected[0].task["_submission"]["source_kind"] == "exp_args.pkl"


def test_write_combined_raw_json_writes_collected_tasks(tmp_path):
    root = tmp_path / "agentlab_results"
    task = {
        "sites": ["jobportal"],
        "task_id": 9,
        "intent": "Combined output task",
        "eval": {"eval_types": ["rubric_verifier"]},
    }
    _write_submission_json(root / "jobportal-submission-9" / "submission.json", task)

    output = write_combined_raw_json(
        collect_submission_tasks(root),
        tmp_path / "raw.json",
    )

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data[0]["task_id"] == 9

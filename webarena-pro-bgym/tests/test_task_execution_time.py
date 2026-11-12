"""Execution time belongs to setup, not a reporting cutoff or regrade."""

from datetime import date
from types import SimpleNamespace

import pytest
from webarena_pro_bgym import run_eval_cli
from webarena_pro_bgym.benchmark import task as task_module
from webarena_pro_core.eval.dag import DAGEvaluator, EvalContext
from webarena_pro_core.task import DEPLOYED_WEBSITE_URLS, WebArenaProTaskConfig


class DummyPage:
    url = "about:blank"

    def goto(self, url, **kwargs):
        self.url = url

    def on(self, *args):
        pass


@pytest.fixture
def execution(monkeypatch):
    class ClockDate(date):
        current = date(2026, 10, 29)

        @classmethod
        def today(cls):
            return cls.current

    clock = {"ns": 1_793_275_200_123_456_789}
    monkeypatch.setattr(task_module, "date", ClockDate)
    monkeypatch.setattr(task_module.time, "time_ns", lambda: clock["ns"])
    monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "0")
    monkeypatch.setattr(
        "webarena_pro_core.state_reset.wait_until_site_ready", lambda site: None
    )
    config = WebArenaProTaskConfig(
        task_id="109",
        intent="Call each person",
        sites=("mattermost",),
        container_name="execution-time-test",
        start_url=DEPLOYED_WEBSITE_URLS["mattermost"],
        evaluation={
            "nodes": [{"id": "saved", "type": "backend_state", "eval_config": {}}]
        },
    )
    task = task_module.WebArenaProTask(seed=0, config=config)
    seen = []

    def evaluate(self, context):
        seen.append(context)
        return 1.0, {"saved": {"passed": True, "reason": "captured context"}}

    monkeypatch.setattr(DAGEvaluator, "evaluate", evaluate)
    return task, config, clock, ClockDate, seen


def test_setup_time_stays_fixed_across_validations_and_refreshes_on_setup(
    execution, monkeypatch
):
    task, _, clock, clock_date, seen = execution
    page = DummyPage()
    ready_times = []
    monkeypatch.setattr(
        "webarena_pro_core.state_reset.wait_until_site_ready",
        lambda site: ready_times.append(task.task_start_time_ms),
    )
    assert task.task_start_time_ms is None
    task.setup(page)
    original_scope = task.judge_cache
    original_ns = clock["ns"]
    # Validation can happen much later (including after midnight), but must
    # still include records created earlier in this execution.
    clock["ns"] += 86_400_000_000_000
    clock_date.current = date(2026, 10, 30)
    task.validate(page, [], budget_checkpoint=True)
    task.validate(page, [], last_action="done()")
    assert [(c.task_start_time_ms, c.task_start_date) for c in seen] == [
        (original_ns // 1_000_000, date(2026, 10, 29)),
        (original_ns // 1_000_000, date(2026, 10, 29)),
    ]
    assert all(c.judge_cache is original_scope for c in seen)

    # Checkpoint recovery also uses a fresh setup, then replays actions into
    # the reset site. The new cutoff precedes those recreated records.
    task.setup(page)
    task.validate(page, [], last_action="done()")
    assert seen[-1].task_start_time_ms == clock["ns"] // 1_000_000
    assert seen[-1].task_start_date == date(2026, 10, 30)
    assert seen[-1].judge_cache is not original_scope
    assert ready_times == [original_ns // 1_000_000, clock["ns"] // 1_000_000]


def test_legacy_validation_without_setup_keeps_unknown_start_time(execution):
    task, _, _, clock_date, seen = execution
    del task.task_start_time_ms  # Older task objects have no execution timestamp.
    task.validate(DummyPage(), [], last_action="done()")
    assert seen[0].task_start_time_ms is None
    assert seen[0].task_start_date == clock_date.current
    assert EvalContext().task_start_time_ms is None


def test_cli_dry_run_does_not_assign_grading_time_to_existing_state(
    execution, monkeypatch
):
    _, config, clock, _, seen = execution
    monkeypatch.setattr(
        run_eval_cli,
        "WebArenaProBenchmark",
        lambda **kwargs: SimpleNamespace(
            env_args_list=[SimpleNamespace(task_config=config)]
        ),
    )
    run_eval_cli.dry_run_eval("mattermost", [109])
    clock["ns"] += 86_400_000_000_000
    run_eval_cli.dry_run_eval("mattermost", [109])
    assert len(seen) == 2
    assert all(context.task_start_time_ms is None for context in seen)
    assert all(context.task_start_date == date.today() for context in seen)

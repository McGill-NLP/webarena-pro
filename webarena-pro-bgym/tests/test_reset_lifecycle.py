"""Task-declared sites drive reset and prewarm, including cross-site task 111."""

from dataclasses import replace

import pytest

from webarena_pro_bgym.benchmark.task import WebArenaProTask
from webarena_pro_bgym.prewarm import prepare_sites
from webarena_pro_core.task import load_task_configs


class Page:
    def __init__(self):
        self.url = "about:blank"

    def on(self, *args):
        pass

    def goto(self, url, **kwargs):
        self.url = url


@pytest.mark.parametrize("multisite", [False, True])
@pytest.mark.parametrize("mode", ["reset", "prewarmed", "stale_prewarm", "reset_disabled"])
def test_task_declared_sites_survive_reset_and_prewarm_transitions(monkeypatch, multisite, mode):
    configs = load_task_configs("mattermost")
    if multisite:
        config = next(task for task in configs if task.task_id == "111")
        expected_sites = ["mattermost", "firefly", "flight-search", "x-lite"]
    else:
        config = next(task for task in configs if task.sites == ("mattermost",))
        expected_sites = ["mattermost"]
    assert list(config.sites) == expected_sites
    config = replace(config, require_login=False, evaluation=None)
    monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", "0" if mode == "reset_disabled" else "1")
    monkeypatch.delenv("WP_PREWARMED_TASK_ID", raising=False)
    # An unrelated site can be allocated in the worker's environment. It is
    # neither reset nor awaited for this task.
    monkeypatch.setenv("WP_NEXTCLOUD_URL", "http://nextcloud--w3.localhost:8080")
    resets, readiness = [], []
    monkeypatch.setattr("webarena_pro_core.state_reset.reset_site", resets.append)
    monkeypatch.setattr("webarena_pro_core.state_reset.wait_until_site_ready", readiness.append)

    if mode == "prewarmed":
        prepare_sites(config.sites, task_id=config.task_id)
        assert resets == expected_sites
        resets.clear()
        monkeypatch.setenv("WP_PREWARMED_TASK_ID", config.task_id)
    elif mode == "stale_prewarm":
        monkeypatch.setenv("WP_PREWARMED_TASK_ID", "unrelated-task")

    task = WebArenaProTask(seed=0, config=config)
    page = Page()
    _, info = task.setup(page)

    assert info["sites"] == expected_sites
    assert page.url == info["start_url"]
    assert task.navigation_guard.last_urls[page] == page.url
    if mode in {"prewarmed", "reset_disabled"}:
        assert resets == []
        assert readiness == expected_sites
    else:
        assert resets == expected_sites
        assert readiness == []  # reset_site owns readiness in this path

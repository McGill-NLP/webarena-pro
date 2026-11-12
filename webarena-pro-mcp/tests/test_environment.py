from webarena_pro_mcp.supervisor import Environment, authenticate


def test_browser_permissions_use_exact_canonical_task_origins():
    import pytest
    from webarena_pro_mcp.supervisor import browser_origins
    from webarena_pro_mcp.tool_policy import PolicyError

    assert browser_origins([
        "http://penpot:9001/", "http://penpot:9001/#/workspace", "https://SITE.test/path",
        "http://[::1]:9002/",
    ]) == ["http://[::1]:9002", "http://penpot:9001", "https://site.test:443"]
    for url in (
        "http://first.test,second.test", "file:///tmp/page", "http://user:pass@site.test",
        "http://*", "http://*.example.com", "http://foo bar", "http://foo\\bar",
        "http://foo%2cbar", "http://[fe80::1%25eth0]",
        "http://foo\nbar", "http://foo\tbar", "http://site.test:0", "http://[::1]suffix",
    ):
        with pytest.raises((ValueError, PolicyError)):
            browser_origins([url])


def test_managed_namespace_resets_all_sites_and_cleans_partial_setup(monkeypatch):
    import os

    import pytest
    from webarena_pro_core import site_env_var_key
    from webarena_pro_core.eval.providers.webdav import (
        deployed_website_urls as provider_urls,
    )
    from webarena_pro_core.task import (
        DEPLOYED_WEBSITE_LOGIN_URLS,
        DEPLOYED_WEBSITE_URLS,
    )

    sites = ("jobportal", "x-lite")
    for site in sites:
        monkeypatch.setitem(DEPLOYED_WEBSITE_URLS, site, DEPLOYED_WEBSITE_URLS[site])
        monkeypatch.setitem(DEPLOYED_WEBSITE_LOGIN_URLS, site, DEPLOYED_WEBSITE_LOGIN_URLS[site])
        for suffix in ("URL", "CONTAINER_NAME", "EXP_HASH", "HOST_PORT"):
            monkeypatch.delenv(f"WP_{site_env_var_key(site)}_{suffix}", raising=False)
    monkeypatch.setenv("WP_URL_MODE", "subdomain")
    # Isolate all direct environment writes performed by the process-local owner.
    monkeypatch.setattr(os, "environ", dict(os.environ))
    events = []

    def reset(site, **_):
        events.append(("reset", site))
        if site == "x-lite":
            raise RuntimeError("fixture startup failure")

    monkeypatch.setattr("webarena_pro_core.state_reset.reset_site", reset)
    monkeypatch.setattr(
        "webarena_pro_core.state_reset.wait_until_site_ready", lambda s: events.append(("ready", s))
    )
    monkeypatch.setattr(
        "webarena_pro_core.state_reset.stop_site_container", lambda s: events.append(("stop", s))
    )
    environment = Environment(sites, "mcp-fixture", False)
    with pytest.raises(RuntimeError):
        environment.setup()
    assert "mcp-fixture" in os.environ["WP_JOBPORTAL_URL"]
    assert provider_urls()["jobportal"] == os.environ["WP_JOBPORTAL_URL"]
    environment.close()
    assert events == [
        ("reset", "jobportal"),
        ("ready", "jobportal"),
        ("reset", "x-lite"),
        ("stop", "x-lite"),
        ("stop", "jobportal"),
    ]


def test_existing_environment_not_removed(monkeypatch):
    events = []
    monkeypatch.setattr(
        "webarena_pro_core.state_reset.reset_site", lambda s, **_: events.append(("reset", s))
    )
    monkeypatch.setattr("webarena_pro_core.state_reset.wait_until_site_ready", lambda s: None)
    monkeypatch.setattr(
        "webarena_pro_core.state_reset.stop_site_container", lambda s: events.append(("stop", s))
    )
    environment = Environment(("jobportal",), "unused", True)
    environment.setup()
    environment.close()
    assert events == [("reset", "jobportal")]


def test_external_environment_updates_urls_without_owning_sidecars(monkeypatch):
    import os
    from unittest.mock import Mock

    from webarena_pro_core.task import DEPLOYED_WEBSITE_LOGIN_URLS, DEPLOYED_WEBSITE_URLS
    from webarena_pro_core.website_metadata import deployed_website_login_urls, deployed_website_urls

    urls = {"jobportal": "http://harbor-jobs", "x-lite": "http://harbor-social"}
    monkeypatch.setattr(os, "environ", dict(os.environ))
    for site in urls:
        monkeypatch.setitem(DEPLOYED_WEBSITE_URLS, site, DEPLOYED_WEBSITE_URLS[site])
        monkeypatch.setitem(DEPLOYED_WEBSITE_LOGIN_URLS, site, DEPLOYED_WEBSITE_LOGIN_URLS[site])
    reset, stop, ready = Mock(), Mock(), Mock()
    monkeypatch.setattr("webarena_pro_core.state_reset.reset_site", reset)
    monkeypatch.setattr("webarena_pro_core.state_reset.stop_site_container", stop)
    monkeypatch.setattr("webarena_pro_core.state_reset.wait_until_site_ready", ready)
    environment = Environment(tuple(urls), "harbor", False, external_urls=urls)
    assert environment.setup() == urls
    assert deployed_website_urls(tuple(urls)) == urls
    assert deployed_website_login_urls(tuple(urls)) == {
        "jobportal": "http://harbor-jobs/accounts/login/",
        "x-lite": "http://harbor-social/login",
    }
    assert {site: DEPLOYED_WEBSITE_URLS[site] for site in urls} == urls
    assert [call.args for call in ready.call_args_list] == [("jobportal",), ("x-lite",)]
    assert all(call.kwargs == {"wait_for_snapshot": False} for call in ready.call_args_list)
    environment.close()
    reset.assert_not_called()
    stop.assert_not_called()


def test_external_environment_rejects_missing_or_extra_sites():
    import pytest

    for urls in ({}, {"x-lite": "http://social"}, {"jobportal": "http://jobs", "x-lite": "http://social"}):
        with pytest.raises(ValueError, match="exactly the task websites"):
            Environment(("jobportal",), "harbor", False, external_urls=urls).setup()


async def test_login_uses_each_tasks_selected_account(monkeypatch, task):
    from unittest.mock import AsyncMock, Mock

    login = Mock(ui_login=AsyncMock())
    constructor = Mock(return_value=login)
    monkeypatch.setattr("webarena_pro_core.autologin.async_api.AutoLogin", constructor)
    task.require_login = True
    task.sites = ("jobportal", "mattermost")
    task.login_usernames = {"jobportal": "alice", "mattermost": "bob"}
    page = object()
    urls = {"jobportal": "http://recruiting.test", "mattermost": "http://chat.test"}
    await authenticate(task, page, urls)
    assert constructor.call_args.kwargs["urls"] == urls
    assert [call.kwargs for call in login.ui_login.await_args_list] == [
        {"site": "jobportal", "page": page, "username": "alice"},
        {"site": "mattermost", "page": page, "username": "bob"},
    ]


def test_managed_media_port_is_not_shared(monkeypatch):
    import os
    from contextlib import contextmanager

    from webarena_pro_core import website_published_ports
    from webarena_pro_core.task import (
        DEPLOYED_WEBSITE_LOGIN_URLS,
        DEPLOYED_WEBSITE_URLS,
    )

    monkeypatch.setattr(
        os,
        "environ",
        {key: value for key, value in os.environ.items() if not key.startswith("WP_MATTERMOST_")},
    )
    monkeypatch.setenv("WP_URL_MODE", "subdomain")
    monkeypatch.setitem(DEPLOYED_WEBSITE_URLS, "mattermost", DEPLOYED_WEBSITE_URLS["mattermost"])
    monkeypatch.setitem(DEPLOYED_WEBSITE_LOGIN_URLS, "mattermost", DEPLOYED_WEBSITE_LOGIN_URLS["mattermost"])
    locked = False

    @contextmanager
    def lock(name):
        nonlocal locked
        assert name == "mcp-additional-ports"
        locked = True
        try:
            yield
        finally:
            locked = False

    def port():
        assert locked
        return 58321

    def reset(*_args, **_kwargs):
        assert locked
        assert website_published_ports("mattermost", use_proxy=True) == {"8443/tcp": 58321, "8443/udp": 58321}

    monkeypatch.setattr("webarena_pro_core.runtime_locks.runtime_lock", lock)
    monkeypatch.setattr("webarena_pro_core.state_reset.reset_site", reset)
    monkeypatch.setattr("webarena_pro_core.state_reset.wait_until_site_ready", lambda *_args: None)
    monkeypatch.setattr("webarena_pro_mcp.supervisor.free_media_port", port)
    Environment(("mattermost",), "mcp-fixture", False).setup()
    assert website_published_ports("mattermost", use_proxy=True) == {"8443/tcp": 58321, "8443/udp": 58321}

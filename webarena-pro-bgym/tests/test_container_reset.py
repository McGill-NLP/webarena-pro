from webarena_pro_bgym.benchmark import container_reset


def test_reset_enabled_defaults_to_true(monkeypatch):
    monkeypatch.delenv("WP_RESET_CONTAINER_PER_TASK", raising=False)

    assert container_reset.reset_enabled() is True


def test_reset_enabled_can_be_disabled(monkeypatch):
    for value in ("0", "false", "no"):
        monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", value)
        assert container_reset.reset_enabled() is False


def test_reset_enabled_accepts_truthy_override(monkeypatch):
    for value in ("1", "true", "yes"):
        monkeypatch.setenv("WP_RESET_CONTAINER_PER_TASK", value)
        assert container_reset.reset_enabled() is True


def test_reset_site_delegates_to_core(monkeypatch):
    calls = []
    monkeypatch.setattr(
        container_reset.core_reset,
        "reset_site",
        lambda site: calls.append(site),
    )

    container_reset.reset_site("nextcloud")

    assert calls == ["nextcloud"]


def test_stop_site_delegates_for_container_backend(monkeypatch):
    calls = []
    monkeypatch.setenv("WP_RESET_BACKEND", "container")
    monkeypatch.setattr(
        container_reset.core_reset,
        "stop_site_container",
        lambda site: calls.append(site),
    )

    container_reset.stop_site("nextcloud")

    assert calls == ["nextcloud"]

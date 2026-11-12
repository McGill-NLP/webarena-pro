import os

from webarena_pro_bgym.parallel import (
    activate_worker_environment,
    build_worker_environment,
    reassign_worker_environment,
    reserve_worker_slot,
    split_task_ids,
    worker_environment_overrides_present,
)
from webarena_pro_core import WEBSITES_ADDITIONAL_PORTS, WEBSITES_HOST_PORTS


def test_build_worker_environment_normalizes_hyphenated_sites():
    env = build_worker_environment(sites=["erp-next"], worker_index=2, base_env={})
    expected_port = WEBSITES_HOST_PORTS["erp-next"] + 2

    assert env["WP_ERP_NEXT_HOST_PORT"] == str(expected_port)
    assert env["WP_ERP_NEXT_URL"] == "http://erp-next--w2.localhost:8080"
    assert env["WP_ERP_NEXT_CONTAINER_NAME"] == "erp-next-w2"
    assert env["WP_ERP_NEXT_EXP_HASH"] == "w2"
    assert env["WP_EXP_HASH"] == "w2"
    assert env["WP_RESET_CONTAINER_PER_TASK"] == "1"
    assert env["WP_RESET_BACKEND"] == "container"


def test_build_worker_environment_can_use_direct_port_urls():
    env = build_worker_environment(
        sites=["erp-next"],
        worker_index=2,
        base_env={"WP_URL_MODE": "port"},
    )
    expected_port = WEBSITES_HOST_PORTS["erp-next"] + 2

    assert env["WP_ERP_NEXT_URL"] == f"http://localhost:{expected_port}"


def test_build_worker_environment_offsets_additional_ports():
    env = build_worker_environment(sites=["peppermint"], worker_index=3, base_env={})
    expected_port = WEBSITES_HOST_PORTS["peppermint"] + 3
    expected_api_port = WEBSITES_ADDITIONAL_PORTS["peppermint"]["5003/tcp"] + 3

    assert env["WP_PEPPERMINT_HOST_PORT"] == str(expected_port)
    assert env["WP_PEPPERMINT_API_HOST_PORT"] == str(expected_api_port)


def test_build_worker_environment_defaults_reset_backend_to_container():
    env = build_worker_environment(
        sites=["jobportal"],
        worker_index=1,
        base_env={"WP_RESET_BACKEND": "state"},
    )

    assert env["WP_RESET_BACKEND"] == "container"


def test_build_worker_environment_sets_all_selected_sites():
    env = build_worker_environment(
        sites=["nextcloud", "mattermost"],
        worker_index=2,
        base_env={},
    )

    assert env["WP_NEXTCLOUD_CONTAINER_NAME"] == "nextcloud-w2"
    assert env["WP_MATTERMOST_CONTAINER_NAME"] == "mattermost-w2"
    assert env["WP_NEXTCLOUD_URL"] == "http://nextcloud--w2.localhost:8080"
    assert env["WP_MATTERMOST_URL"] == "http://mattermost--w2.localhost:8080"


def test_build_worker_environment_requires_sites():
    import pytest

    with pytest.raises(ValueError, match="at least one"):
        build_worker_environment(sites=[], worker_index=0, base_env={})


def test_reassign_worker_environment_shifts_existing_slot_ports():
    base = build_worker_environment(
        sites=["nextcloud", "peppermint"],
        worker_index=3,
        base_env={"WP_URL_MODE": "port"},
    )

    reassigned = reassign_worker_environment(
        sites=["nextcloud", "peppermint"],
        from_worker_index=3,
        to_worker_index=7,
        base_env=base,
    )

    assert reassigned["WP_NEXTCLOUD_HOST_PORT"] == str(
        WEBSITES_HOST_PORTS["nextcloud"] + 7
    )
    assert reassigned["WP_NEXTCLOUD_URL"] == (
        f"http://localhost:{WEBSITES_HOST_PORTS['nextcloud'] + 7}"
    )
    assert reassigned["WP_NEXTCLOUD_CONTAINER_NAME"] == "nextcloud-w7"
    assert reassigned["WP_PEPPERMINT_API_HOST_PORT"] == str(
        WEBSITES_ADDITIONAL_PORTS["peppermint"]["5003/tcp"] + 7
    )
    assert reassigned["WP_EXP_HASH"] == "w7"
    assert reassigned["WP_ACTIVE_RUNTIME_SLOT"] == "7"


def test_activate_worker_environment_switches_only_runtime_overrides(monkeypatch):
    original_env = dict(os.environ)
    try:
        monkeypatch.setenv("UNCHANGED", "yes")
        env = build_worker_environment(
            sites=["mattermost"], worker_index=4, base_env={}
        )
        env["WP_ACTIVE_RUNTIME_SLOT"] = "4"

        activate_worker_environment(sites=["mattermost"], env=env)

        assert os.environ["WP_MATTERMOST_CONTAINER_NAME"] == "mattermost-w4"
        assert os.environ["WP_ACTIVE_RUNTIME_SLOT"] == "4"
        assert os.environ["UNCHANGED"] == "yes"
    finally:
        os.environ.clear()
        os.environ.update(original_env)


def test_split_task_ids_round_robin():
    assert split_task_ids([1, 2, 3, 4, 5], 2) == [[1, 3, 5], [2, 4]]


def test_worker_environment_overrides_present_detects_selected_site_only():
    env = {
        "WP_MATTERMOST_CONTAINER_NAME": "mattermost-w0",
        "WP_NEXTCLOUD_URL": "http://nextcloud--w0.localhost:8080",
    }

    assert worker_environment_overrides_present(sites=["mattermost"], env=env) is True
    assert worker_environment_overrides_present(sites=["thunderbird"], env=env) is False


def test_reserve_worker_slot_uses_next_free_index_for_overlapping_sites(tmp_path):
    slot0 = reserve_worker_slot(sites=["mattermost"], lock_root=tmp_path)
    try:
        slot1 = reserve_worker_slot(sites=["mattermost"], lock_root=tmp_path)
        try:
            assert slot0.worker_index == 0
            assert slot1.worker_index == 1
        finally:
            slot1.release()
    finally:
        slot0.release()

def test_reserve_worker_slot_shares_index_across_selected_sites(tmp_path):
    slot0 = reserve_worker_slot(
        sites=["nextcloud", "mattermost"],
        lock_root=tmp_path,
    )
    try:
        slot1 = reserve_worker_slot(sites=["mattermost"], lock_root=tmp_path)
        try:
            assert slot0.worker_index == 0
            assert slot1.worker_index == 1
        finally:
            slot1.release()
    finally:
        slot0.release()


def test_exact_runtime_slot_reservation_does_not_fall_back_or_steal(tmp_path):
    import pytest

    held = reserve_worker_slot(sites=["mattermost"], worker_index=5, lock_root=tmp_path)
    try:
        assert held.worker_index == 5
        with pytest.raises(RuntimeError, match="Could not reserve"):
            reserve_worker_slot(sites=["nextcloud", "mattermost"], worker_index=5, lock_root=tmp_path)
        assert (tmp_path / "mattermost" / "w5" / "owner.pid").exists()
        assert not (tmp_path / "nextcloud" / "w5").exists()
        assert not (tmp_path / "mattermost" / "w0").exists()
    finally:
        held.release()
    reclaimed = reserve_worker_slot(sites=["mattermost"], worker_index=5, lock_root=tmp_path)
    reclaimed.release()


def test_exact_runtime_slot_validates_index(tmp_path):
    import pytest

    for index in (-1, True, 1.5):
        with pytest.raises(ValueError, match="nonnegative integer"):
            reserve_worker_slot(sites=["mattermost"], worker_index=index, lock_root=tmp_path)


def test_calls_workers_share_udp_tcp_port_and_keep_custom_base(monkeypatch):
    from webarena_pro_core import website_environment, website_published_ports

    env = build_worker_environment(
        sites=["mattermost"], worker_index=3,
        base_env={"WP_MATTERMOST_CALLS_HOST_PORT": "18443",
                  "WP_MATTERMOST_CALLS_HOST": "192.0.2.20"},
    )
    assert env["WP_MATTERMOST_CALLS_HOST_PORT"] == "18446"
    assert env["WP_MATTERMOST_CALLS_HOST"] == "192.0.2.20"
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    assert website_published_ports("mattermost") == {
        "8443/tcp": 18446, "8443/udp": 18446,
    }
    assert website_environment("mattermost")["MM_CALLS_ICE_HOST_PORT_OVERRIDE"] == "18446"

    moved = reassign_worker_environment(
        sites=["mattermost"], from_worker_index=3, to_worker_index=8,
        base_env=env,
    )
    # Both protocols share one environment variable; shift it only once.
    assert moved["WP_MATTERMOST_CALLS_HOST_PORT"] == "18451"


def test_peppermint_custom_api_port_survives_worker_reassignment(monkeypatch):
    from webarena_pro_core import website_published_ports

    env = build_worker_environment(
        sites=["peppermint"], worker_index=3,
        base_env={"WP_URL_MODE": "port", "WP_PEPPERMINT_API_HOST_PORT": "15003"},
    )
    moved = reassign_worker_environment(
        sites=["peppermint"], from_worker_index=3, to_worker_index=7,
        base_env=env,
    )
    for key, value in moved.items():
        monkeypatch.setenv(key, value)
    assert website_published_ports("peppermint") == {
        "3000/tcp": WEBSITES_HOST_PORTS["peppermint"] + 7,
        "5003/tcp": 15010,
    }

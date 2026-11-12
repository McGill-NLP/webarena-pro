from pathlib import Path

from webarena_pro_core.config import WEBSITE_CREDENTIALS


PRIMARY_USERS = {"maya.patel", "daniel.brooks"}


def test_agentlab_facing_nextcloud_credentials_use_named_accounts() -> None:
    credentials = WEBSITE_CREDENTIALS["nextcloud"]

    assert {entry["username"] for entry in credentials if entry["username"] != "admin"} == PRIMARY_USERS
    assert all(entry["password"] == "agentpass" for entry in credentials if entry["username"] in PRIMARY_USERS)


def test_active_task_configs_have_no_legacy_nextcloud_login_maps() -> None:
    package_root = (
        Path(__file__).resolve().parents[2]
        / "webarena-pro-core"
        / "src"
        / "webarena_pro_core"
    )
    for config_path in (package_root / "config").glob("*.json"):
        content = config_path.read_text(encoding="utf-8")
        assert '"nextcloud": "agent1"' not in content, config_path
        assert '"nextcloud": "agent2"' not in content, config_path

    for config_path in (
        package_root / "config" / "nextcloud.raw.json",
    ):
        content = config_path.read_text(encoding="utf-8")
        assert "agent1" not in content, config_path
        assert "agent2" not in content, config_path

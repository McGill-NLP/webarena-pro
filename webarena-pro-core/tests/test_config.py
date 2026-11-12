from webarena_pro_core import (
    WEBSITES_CONTAINER_PORTS,
    WEBSITES_FIXED_URLS,
    WEBSITES_HOST_PORTS,
    WEBSITES_IMAGES,
    active_exp_hash,
    build_website_url,
    build_website_ports,
    container_name_for_site,
    labels_for_site,
    site_env_var_key,
    website_environment,
    website_hostname,
    website_subdomain_label,
)
from webarena_pro_core.config import (
    get_login_credentials,
    get_website_credentials,
)


def test_websites_fixed_urls_are_subdomain_routes_by_default():
    assert WEBSITES_FIXED_URLS["nextcloud"] == "http://nextcloud--local.localhost:8080"
    assert WEBSITES_FIXED_URLS["erp-next"] == "http://erp-next--local.localhost:8080"


def test_build_website_url_supports_direct_port_mode():
    for site, port in WEBSITES_HOST_PORTS.items():
        assert build_website_url(site, mode="port") == f"http://localhost:{port}"


def test_build_website_url_includes_custom_exp_hash_and_domain():
    assert (
        build_website_url("nextcloud", exp_hash="run_42", base_domain="example.test")
        == "http://nextcloud--run-42.example.test:8080"
    )


def test_web_server_url_without_port_uses_scheme_default(monkeypatch):
    monkeypatch.setenv("WP_WEB_SERVER_URL", "http://213.0.113.10.sslip.io")
    monkeypatch.delenv("WP_WEB_SERVER_PORT", raising=False)

    assert (
        build_website_url("nextcloud")
        == "http://nextcloud--local.213.0.113.10.sslip.io"
    )


def test_https_web_server_url_without_port_uses_scheme_default(monkeypatch):
    monkeypatch.setenv("WP_WEB_SERVER_URL", "https://webarena.example.test")
    monkeypatch.delenv("WP_WEB_SERVER_PORT", raising=False)

    assert (
        build_website_url("nextcloud")
        == "https://nextcloud--local.webarena.example.test"
    )


def test_website_hostname_uses_dns_safe_label():
    assert (
        website_hostname("erp-next", exp_hash="ABC_123", base_domain="localhost")
        == "erp-next--abc-123.localhost"
    )
    assert website_subdomain_label("nextcloud", exp_hash="run 42") == "nextcloud--run-42"


def test_nextcloud_environment_trusts_worker_subdomain():
    environment = website_environment("nextcloud", exp_hash="w0")

    assert environment == {
        "WP_NEXTCLOUD_URL": "http://nextcloud--w0.localhost:8080",
        "WP_NEXTCLOUD_HOST_PORT": "8080",
        "NEXTCLOUD_TRUSTED_DOMAINS": (
            "localhost * 127.0.0.1 nextcloud--w0.localhost "
            "nextcloud--w0.localhost:8080"
        ),
    }


def test_website_environment_forwards_eval_token(monkeypatch):
    monkeypatch.setenv("WP_EVAL_TOKEN", "secret-token")

    assert website_environment("travelmap") == {
        "WP_EVAL_TOKEN": "secret-token",
    }
    assert website_environment("firefly") == {
        "WP_EVAL_TOKEN": "secret-token",
        "APP_URL": "http://firefly--local.localhost:8080",
        "ASSET_URL": "http://firefly--local.localhost:8080",
    }


def test_active_exp_hash_reads_exp_hash_env(monkeypatch):
    monkeypatch.setenv("WP_EXP_HASH", "run-from-exp")

    assert active_exp_hash() == "run-from-exp"


def test_container_name_defaults_to_site_for_local_hash():
    assert container_name_for_site("nextcloud", exp_hash="local") == "nextcloud"
    assert container_name_for_site("nextcloud", exp_hash="run42") == "nextcloud--run42"


def test_labels_include_site_hash_and_upstream_port():
    labels = labels_for_site("mattermost", exp_hash="run42")

    assert labels["webarena-pro-core.managed"] == "website"
    assert labels["webarena-pro-core.site"] == "mattermost"
    assert labels["webarena-pro-core.exp-hash"] == "run42"
    assert labels["webarena-pro-core.upstream-port"] == "8065"


def test_get_website_credentials_returns_dict_for_known_site():
    credentials = get_website_credentials("nextcloud")

    assert credentials == {
        "maya_username": "maya.patel",
        "maya_password": "agentpass",
        "daniel_username": "daniel.brooks",
        "daniel_password": "agentpass",
    }


def test_get_website_credentials_returns_minerva_lite_login():
    credentials = get_website_credentials("minerva-lite")

    assert credentials is not None
    assert credentials["student_id"] == "260123456"
    assert credentials["student_password"] == "mcgill123"
    assert credentials["advisor_id"] == "9801001"
    assert credentials["advisor_password"] == "advisor123"


def test_get_website_credentials_returns_none_for_unknown_site():
    assert get_website_credentials("unknown-site") is None


def test_get_login_credentials_returns_all_known_accounts():
    credentials = get_login_credentials("peppermint")

    assert {credential["username"] for credential in credentials} >= {
        "james@peppermint.local",
        "priya@peppermint.local",
        "admin@admin.com",
    }


def test_site_env_var_key_normalizes_hyphenated_names():
    assert site_env_var_key("erp-next") == "ERP_NEXT"
    assert site_env_var_key("x-lite") == "X_LITE"


def test_build_website_ports_offsets_additional_ports():
    ports = build_website_ports("peppermint", host_port=3010, port_offset=2)

    assert ports["3000/tcp"] == 3010
    assert ports["5003/tcp"] == 5005


def test_yt_lite_publishes_app_container_port():
    assert WEBSITES_CONTAINER_PORTS["yt-lite"] == 7860
    assert build_website_ports("yt-lite", host_port=7201) == {"7860/tcp": 7201}

import pytest

from webarena_pro_core import website_environment


def test_pipedrive_auth_callbacks_use_worker_origin():
    settings = website_environment("pipedrive", public_url="http://pipedrive:4520", eval_token="fixture")
    assert settings["NEXTAUTH_URL"] == "http://pipedrive:4520"


def test_penpot_http_session_cookie_and_existing_flags(monkeypatch):
    monkeypatch.setenv("PENPOT_FLAGS", "enable-login-with-password enable-secure-session-cookies disable-smtp")
    settings = website_environment("penpot", public_url="http://penpot:9001", eval_token="fixture")
    flags = settings["PENPOT_FLAGS"].split()
    assert "disable-secure-session-cookies" in flags
    assert "enable-secure-session-cookies" not in flags
    assert "enable-login-with-password" in flags
    assert "disable-smtp" in flags


def test_penpot_https_keeps_image_cookie_policy(monkeypatch):
    monkeypatch.delenv("PENPOT_FLAGS", raising=False)
    settings = website_environment("penpot", public_url="https://penpot.example", eval_token="fixture")
    assert "PENPOT_FLAGS" not in settings
    assert settings["PENPOT_PUBLIC_URI"] == "https://penpot.example/"


@pytest.mark.parametrize(
    "site,key",
    [("nextcloud", "WP_NEXTCLOUD_URL"), ("metabase", "MB_SITE_URL"), ("firefly", "APP_URL")],
)
def test_external_orchestrator_url_and_token(site, key, monkeypatch):
    def forbidden():
        raise AssertionError("An explicit token must not read local credentials")

    monkeypatch.setattr("webarena_pro_core.eval_token.resolve_eval_token", forbidden)
    monkeypatch.setenv("WP_EVAL_TOKEN", "host-secret")
    settings = website_environment(site, public_url=f"http://{site}:8080", eval_token="runtime-reference")
    assert settings[key] == f"http://{site}:8080"
    assert settings["WP_EVAL_TOKEN"] == "runtime-reference"

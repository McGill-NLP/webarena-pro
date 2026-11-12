import re

import pytest

from webarena_pro_core.nginx import NginxRoute, render_nginx_config


@pytest.mark.parametrize(
    ("configured_port", "server_url", "expected_port"),
    [
        (None, None, 8080),
        ("8080", None, 8080),
        ("18081", None, 18081),
        ("80", None, 80),
        ("18081", "http://localhost:9090", 9090),
        ("18081", "http://localhost", 80),
        ("18081", "https://localhost", 443),
    ],
)
def test_website_and_dashboard_forward_public_port(
    monkeypatch, configured_port, server_url, expected_port
):
    for name, value in (
        ("WP_WEB_SERVER_PORT", configured_port),
        ("WP_WEB_SERVER_URL", server_url),
    ):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)

    config = render_nginx_config(
        [
            NginxRoute(
                site="nextcloud",
                exp_hash="local",
                hostname="nextcloud--local.localhost",
                container_name="nextcloud",
                upstream_port=80,
            ),
        ],
        dashboard_upstream="http://host.docker.internal:18080",
    )

    # Both upstreams must see the public port even though Nginx listens on 80.
    assert config.count("listen 80;") == 2
    assert re.findall(r"proxy_set_header X-Forwarded-Port ([^;]+);", config) == [
        str(expected_port),
        str(expected_port),
    ]

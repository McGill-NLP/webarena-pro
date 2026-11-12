from webarena_pro_core.nginx import NginxRoute, render_nginx_config


def test_render_nginx_config_routes_each_hostname_to_container():
    config = render_nginx_config(
        [
            NginxRoute(
                site="nextcloud",
                exp_hash="local",
                hostname="nextcloud--local.localhost",
                container_name="nextcloud",
                upstream_port=80,
            ),
            NginxRoute(
                site="mattermost",
                exp_hash="w2",
                hostname="mattermost--w2.localhost",
                container_name="mattermost-w2",
                upstream_port=8065,
            ),
        ],
        dashboard_upstream="http://host.docker.internal:18080",
    )

    assert "server_names_hash_bucket_size 128;" in config
    assert "server_name nextcloud--local.localhost;" in config
    assert "set $webarena_upstream http://nextcloud:80;" in config
    assert "server_name mattermost--w2.localhost;" in config
    assert "set $webarena_upstream http://mattermost-w2:8065;" in config
    assert config.count("proxy_pass $webarena_upstream;") == 2
    assert config.count("resolver 127.0.0.11 valid=5s;") == 2
    assert config.count("resolver_timeout 5s;") == 2
    # Website names never occur in literal proxy_pass directives: removing a
    # container between validation and asynchronous reload cannot break parsing.
    assert "proxy_pass http://nextcloud" not in config
    assert "proxy_pass http://mattermost" not in config
    assert "server_name dashboard.localhost;" in config
    assert "proxy_pass http://host.docker.internal:18080;" in config
    assert "X-Forwarded-Host $http_host;" in config

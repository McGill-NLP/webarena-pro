"""Opt-in Docker regressions: python test_runtime.py --image IMAGE.

Requires the local webarena-pro-core package. All containers, volumes and ports
are isolated; the site's normal container manager and shared proxy are unused.
"""

import argparse
import json
import os
import socket
import subprocess
import unittest
import uuid
from urllib.request import Request, urlopen

from webarena_pro_core.state_reset import wait_until_site_ready


def docker(*args, check=True):
    return subprocess.run(
        ["docker", *args], check=check, text=True, capture_output=True, timeout=300
    )


def remove_owned(kind, name, owner):
    result = docker(kind, "inspect", name, check=False)
    if result.returncode:
        return  # Startup may have failed before creating this resource.
    details = json.loads(result.stdout)[0]
    labels = details.get("Config", {}).get("Labels") if kind == "container" else details.get("Labels")
    if (labels or {}).get("codex.nextcloud.owner") != owner:
        raise RuntimeError(f"Refusing to remove unowned {kind}: {name}")
    if kind == "container":
        docker("rm", "-f", "-v", details["Id"])
    else:
        docker("volume", "rm", name)


class RuntimeTests(unittest.TestCase):
    image = ""

    @classmethod
    def setUpClass(cls):
        cls.name = f"nextcloud-runtime-test-{uuid.uuid4().hex[:12]}"
        cls.volume = f"{cls.name}-html"
        docker("volume", "create", "--label", f"codex.nextcloud.owner={cls.name}", cls.volume)
        cls.addClassCleanup(remove_owned, "volume", cls.volume, cls.name)
        cls.addClassCleanup(remove_owned, "container", cls.name, cls.name)
        # nocopy exercises the source+snapshot restoration path even when the
        # image already contains a complete /var/www/html tree.
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        cls.public_url = f"http://nextcloud.runtime.test:{port}"
        cls.reset_url = f"http://reset.runtime.test:{port}"
        docker(
            "run", "-d", "--name", cls.name,
            "--label", f"codex.nextcloud.owner={cls.name}",
            "-p", f"127.0.0.1:{port}:80",
            "--memory", "3g", "--cpus", "1.5",
            # Keep the image health command, with faster failure sampling in tests.
            "--health-interval", "1s", "--health-start-period", "5s", "--health-retries", "1",
            "--mount", f"type=volume,src={cls.volume},dst=/var/www/html,volume-nocopy",
            "-e", f"WP_NEXTCLOUD_URL={cls.public_url}",
            "-e", "WP_NEXTCLOUD_HOST_PORT=80", cls.image,
        )
        details = json.loads(docker("inspect", cls.name).stdout)[0]
        port = details["NetworkSettings"]["Ports"]["80/tcp"][0]["HostPort"]
        cls.url = f"http://127.0.0.1:{port}"
        cls.healthcheck = details["Config"]["Healthcheck"]["Test"]
        previous = os.environ.get("WP_NEXTCLOUD_URL")
        os.environ["WP_NEXTCLOUD_URL"] = cls.url
        cls.addClassCleanup(cls.restore_url, previous)
        try:
            cls.wait_ready()
        except Exception:
            logs = docker("logs", cls.name, check=False)
            print(logs.stdout + logs.stderr)
            raise

    @staticmethod
    def restore_url(previous):
        if previous is None:
            os.environ.pop("WP_NEXTCLOUD_URL", None)
        else:
            os.environ["WP_NEXTCLOUD_URL"] = previous

    @classmethod
    def shell(cls, command, *, check=True, public_url=None):
        env = ["-e", f"WP_NEXTCLOUD_URL={public_url}"] if public_url else []
        return docker("exec", *env, cls.name, "bash", "-euo", "pipefail", "-c", command, check=check)

    @classmethod
    def wait_ready(cls):
        # Actual runner HTTP readiness (/login + password sentinel). Snapshot
        # presence is checked explicitly on our unique container below.
        wait_until_site_ready("nextcloud", timeout_seconds=180, wait_for_snapshot=False)
        cls.shell("test -f /opt/webarena-seed/ready && test -f /var/www/html/data/.webarena-seed-v2.ready")

    def assert_runtime(self, public_url):
        self.wait_ready()
        config = json.loads(self.shell(
            'php -r \'include "/var/www/html/config/config.php"; echo json_encode($CONFIG);\''
        ).stdout)
        self.assertEqual(config["overwrite.cli.url"], public_url)
        host = public_url.split("://", 1)[1]
        self.assertIn(host, config["trusted_domains"])
        with urlopen(Request(f"{self.url}/login", headers={"Host": host}), timeout=10) as response:
            self.assertEqual(response.status, 200)
            self.assertIn("password", response.read().decode().lower())
        owners = self.shell(
            "find /var/www/html/config /var/www/html/data /var/www/html/.htaccess "
            "\\( ! -user www-data -o ! -group www-data \\) -print -quit"
        ).stdout
        self.assertEqual(owners, "")
        htaccess = self.shell("cat /var/www/html/.htaccess").stdout
        self.assertIn("RewriteRule . index.php", htaccess)
        self.assertIn("RewriteBase /", htaccess)
        self.assertEqual(self.healthcheck[0], "CMD-SHELL")
        self.shell(self.healthcheck[1])

    def test_1_fresh_volume(self):
        self.assert_runtime(self.public_url)
        # Explicit trusted domains need not include localhost/127.0.0.1. The
        # healthcheck must still probe the login route with a trusted Host.
        self.shell("""php -r '
            $path = "/var/www/html/config/config.php";
            include $path;
            $CONFIG["trusted_domains"] = ["nextcloud.runtime.test", "reset.runtime.test", "localhost"];
            file_put_contents($path, "<?php\\n\\$CONFIG = " . var_export($CONFIG, true) . ";\\n");
        '""")
        try:
            self.shell(self.healthcheck[1])
        finally:
            self.shell("/seedDir/docker-entrypoint-preseeded.sh true")
            self.wait_ready()

    def test_2_reset_repairs_distribution_rules_and_root_owned_snapshot(self):
        self.shell(
            "cp /usr/src/nextcloud/.htaccess /var/www/html/.htaccess; "
            "chown root:root /var/www/html/.htaccess; "
            "chown -R root:root /opt/webarena-seed/tree/config /opt/webarena-seed/tree/data; "
            "touch /var/www/html/data/should-disappear-on-reset"
        )
        with urlopen(f"{self.url}/status.php", timeout=10) as response:
            self.assertEqual(response.status, 200)
        self.assertNotEqual(self.shell(self.healthcheck[1], check=False).returncode, 0)
        result = self.shell(
            "bash /usr/local/bin/webarena-reset-state",
            public_url=self.reset_url,
        )
        self.assertIn("[nextcloud-reset] Done.", result.stdout)
        self.shell("test ! -e /var/www/html/data/should-disappear-on-reset")
        self.assert_runtime(self.reset_url)

    def test_3_reset_recreates_missing_htaccess(self):
        self.shell("rm /var/www/html/.htaccess; bash /usr/local/bin/webarena-reset-state")
        self.assert_runtime(self.public_url)

    def test_4_regeneration_failure_is_visible_and_fails_reset(self):
        self.shell("chmod 0444 /var/www/html/.htaccess")
        try:
            result = self.shell("bash /usr/local/bin/webarena-reset-state", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Failed to regenerate /var/www/html/.htaccess as www-data", result.stderr)
            self.assertNotIn("[nextcloud-reset] Done.", result.stdout)
            # Startup uses the same repair and must also stop before Apache.
            result = self.shell("/seedDir/docker-entrypoint-preseeded.sh true", check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("Failed to regenerate", result.stderr)
        finally:
            self.shell("chmod 0644 /var/www/html/.htaccess; bash /usr/local/bin/webarena-reset-state")
        self.assert_runtime(self.public_url)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Locally built preseeded Nextcloud image")
    args, remaining = parser.parse_known_args()
    RuntimeTests.image = args.image
    unittest.main(argv=[__file__, *remaining], verbosity=2)

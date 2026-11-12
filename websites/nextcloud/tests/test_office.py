"""Opt-in Office browser and reset regression against a locally built image."""
import argparse
from io import BytesIO
import json
from pathlib import Path
import time
import unittest
import zipfile

import requests
from playwright.sync_api import expect, sync_playwright

import test_runtime as runtime


class OfficeTests(runtime.RuntimeTests):
    evidence = Path("/tmp/nextcloud-office-evidence")

    def assert_urls(self):
        config = json.loads(self.shell("runuser -u www-data -- php occ config:list richdocuments").stdout)["apps"]["richdocuments"]
        self.assertEqual(config["wopi_url"], self.public_url + "/custom_apps/richdocumentscode/proxy.php?req=")
        self.assertEqual(config["public_wopi_url"], self.public_url)
        self.assertEqual(config["wopi_callback_url"], "http://localhost")
        hosts = json.loads(self.shell("cat /tmp/richdocumentscode-33/coolwsd-hosts.json").stdout)
        self.assertEqual(hosts["wopiHosts"], ["localhost"])
        self.shell("test -f /tmp/webarena-office.ready")

    def exercise_spreadsheet(self, browser, phase):
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        page = context.new_page()
        page.set_default_timeout(30_000)
        diagnostics = {"browser": browser.version, "phase": phase, "errors": []}
        page.on("pageerror", lambda error: diagnostics["errors"].append(str(error)))
        name = f"office-{phase}.xlsx"
        contents = f"Office smoke {phase}"
        try:
            page.goto(self.public_url + "/login", wait_until="domcontentloaded")
            page.locator("#user").fill("maya.patel")
            page.locator("#password").fill("agentpass")
            page.locator("button[type=submit]").click()
            page.wait_for_url("**/apps/**")
            page.goto(self.public_url + "/apps/files/", wait_until="domcontentloaded")
            page.get_by_role("button", name="New", exact=True).click()
            page.get_by_text("New spreadsheet", exact=True).click()
            page.get_by_role("textbox", name="Filename").fill(name)
            page.get_by_role("button", name="Create", exact=True).click()
            frame = page.frame_locator('iframe[name^="collaboraframe"]')
            box = frame.get_by_role("combobox", name="Name Box", exact=True)
            box.wait_for(state="visible", timeout=60_000)
            skip = frame.get_by_role("button", name="Skip", exact=True)
            if skip.is_visible():
                skip.click()
            box.fill("A1")
            box.press("Enter")
            formula = frame.get_by_role("textbox", name="Formula bar", exact=True)
            formula.fill(contents)
            formula.press("Enter")
            formula.press("Control+s")
            editor_url = page.url
            frame.locator("body").press("Control+s")
            # UI editing must persist an actual XLSX, not just create a filename.
            dav = f"{self.url}/remote.php/dav/files/maya.patel/{name}"
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                response = requests.get(dav, auth=("maya.patel", "agentpass"), timeout=5)
                if response.status_code == 200 and zipfile.is_zipfile(BytesIO(response.content)):
                    with zipfile.ZipFile(BytesIO(response.content)) as workbook:
                        xml = b"".join(workbook.read(member) for member in workbook.namelist() if member.endswith(".xml"))
                    if contents.encode() in xml:
                        break
                page.wait_for_timeout(500)
            else:
                self.fail("Edited spreadsheet was not persisted through WebDAV within 30s")
            page.goto(self.public_url + "/apps/files/", wait_until="domcontentloaded")
            page.goto(editor_url, wait_until="domcontentloaded")
            box.wait_for(state="visible", timeout=60_000)
            box.fill("A1")
            box.press("Enter")
            expect(formula).to_contain_text(contents, timeout=15_000)
            page.screenshot(path=str(self.evidence / f"{phase}-spreadsheet.png"))
            diagnostics["result"] = "passed"
        except Exception:
            diagnostics["result"] = "failed"
            try:
                page.screenshot(path=str(self.evidence / f"{phase}-failure.png"), timeout=5000)
            except Exception:
                pass  # Preserve the original browser failure if capture also fails.
            raise
        finally:
            (self.evidence / f"{phase}-browser.json").write_text(json.dumps(diagnostics, indent=2))
            context.close()

    def test_0_spreadsheet_before_and_after_reset(self):
        self.evidence.mkdir(parents=True, exist_ok=True)
        self.assert_urls()
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=["--host-resolver-rules=MAP nextcloud.runtime.test 127.0.0.1", "--disable-dev-shm-usage"])
            try:
                self.exercise_spreadsheet(browser, "fresh")
                result = self.shell("timeout --kill-after=5 240 bash /usr/local/bin/webarena-reset-state")
                (self.evidence / "reset.log").write_text(result.stdout + result.stderr)
                self.assert_urls()
                response = requests.get(f"{self.url}/remote.php/dav/files/maya.patel/office-fresh.xlsx", auth=("maya.patel", "agentpass"), timeout=5)
                self.assertEqual(response.status_code, 404)
                self.exercise_spreadsheet(browser, "reset")
            finally:
                browser.close()

    def test_5_external_url_overrides_survive_activation_and_reset(self):
        # Reuse CODE only as the discovery server to exercise the real upstream
        # activate-config command with distinct internal/public/callback URLs.
        # This validates configuration, not an external browser deployment.
        env = [
            "-e", "WP_COLLABORA_URL=https://office.example.test",
            "-e", "WP_COLLABORA_INTERNAL_URL=http://localhost/custom_apps/richdocumentscode/proxy.php?req=",
            "-e", "WP_NEXTCLOUD_CALLBACK_URL=http://callback.example.test",
        ]
        try:
            for command in ("/seedDir/office-ready.sh", "/usr/local/bin/webarena-reset-state"):
                runtime.docker("exec", *env, self.name, "timeout", "--kill-after=5", "240", "bash", command)
                config = json.loads(self.shell("runuser -u www-data -- php occ config:list richdocuments").stdout)["apps"]["richdocuments"]
                self.assertEqual(config["wopi_url"], "http://localhost/custom_apps/richdocumentscode/proxy.php?req=")
                self.assertEqual(config["public_wopi_url"], "https://office.example.test")
                self.assertEqual(config["wopi_callback_url"], "http://callback.example.test")
        finally:
            self.shell("timeout --kill-after=5 240 bash /usr/local/bin/webarena-reset-state")

    def test_6_dead_office_is_unhealthy_and_reset_recovers(self):
        self.shell("pid=$(cat /tmp/richdocumentscode-33/coolwsd.pid); test $(cat /proc/$pid/comm) = coolwsd; kill -TERM $pid")
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if requests.get(self.url + "/webarena-office-health.php", timeout=3).status_code == 503:
                break
            time.sleep(0.2)
        else:
            self.fail("Dead CODE process left Office readiness healthy")
        self.assertNotEqual(self.shell(self.healthcheck[1], check=False).returncode, 0)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            health = json.loads(runtime.docker("inspect", self.name).stdout)[0]["State"]["Health"]["Status"]
            if health == "unhealthy":
                break
            time.sleep(0.5)
        else:
            self.fail("Docker did not mark the dead Office service unhealthy")
        self.shell("timeout --kill-after=5 240 bash /usr/local/bin/webarena-reset-state")
        self.wait_ready()
        self.shell(self.healthcheck[1])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args, remaining = parser.parse_known_args()
    OfficeTests.image = args.image
    OfficeTests.evidence = args.evidence_dir
    unittest.main(argv=[__file__, *remaining], verbosity=2)

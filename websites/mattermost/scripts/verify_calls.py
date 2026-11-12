#!/usr/bin/env python3
"""Exercise native Calls in an explicitly supplied disposable Mattermost fixture.

Requires Playwright Chromium and requests. No fake media, permission overrides,
or CSP overrides are used. Optional reset requires an exact fixture label and
runs the whole flow again afterward. Screenshots/logs go only to --output.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import time

import requests
from playwright.sync_api import sync_playwright


def docker(*args, check=True):
    return subprocess.run(["docker", *args], text=True, capture_output=True, check=check)


def container_meta(name):
    return json.loads(docker("inspect", name).stdout)[0]


def wait_until(check, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(0.2)
    raise AssertionError("Timed out waiting for the expected fixture state")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-rtc-host", default="127.0.0.1")
    parser.add_argument("--expected-rtc-port", type=int, required=True)
    parser.add_argument("--reset-container", help="Explicit disposable fixture to reset")
    parser.add_argument("--reset-label", help="Required ownership label key=value for reset")
    parser.add_argument("--delay-supervisor", action="store_true",
                        help="Pause fixture PID 1 briefly to exercise the reset handshake")
    parser.add_argument("--recipient", action="append", dest="recipients",
                        help="Default: both emma.davis and bob.wilson")
    args = parser.parse_args()
    args.recipients = args.recipients or ["emma.davis", "bob.wilson"]
    base = args.url.rstrip("/")
    args.output.mkdir(parents=True, exist_ok=True)
    if args.reset_container:
        if not args.reset_label or "=" not in args.reset_label:
            parser.error("--reset-container requires --reset-label key=value")
        key, value = args.reset_label.split("=", 1)
        assert container_meta(args.reset_container)["Config"]["Labels"].get(key) == value

    session = requests.Session()

    def login_api():
        response = session.post(base + "/api/v4/users/login",
                                json={"login_id": "admin", "password": "Admin@Secure123"}, timeout=30)
        response.raise_for_status()
        session.headers["Authorization"] = "Bearer " + response.headers["Token"]
        return response.json()["id"]

    caller = login_api()

    def get_posts(channel_id):
        response = session.get(base + f"/api/v4/channels/{channel_id}/posts?per_page=200", timeout=30)
        if response.status_code == 404:
            return []
        response.raise_for_status()
        return list(response.json()["posts"].values())

    def open_dm(page, username):
        page.locator("#newDirectMessageButton").click()
        search = page.get_by_role("dialog").locator("input[type=text]")
        search.fill(username)
        page.get_by_label("Add option " + username, exact=True).click()
        page.locator("#saveItems").click()

    def connected(page):
        # wait_for_function uses eval() blocked by Mattermost's CSP in older
        # Playwright releases. Poll a read-only evaluation without changing CSP.
        wait_until(lambda: page.evaluate("window.callsClient?.connected === true"), timeout=30)
        stats = {}
        selected = []

        def nominated_pair_ready():
            nonlocal stats, selected
            stats = page.evaluate("async () => await window.callsClient.getStats()")
            selected = [pair for pair in stats["rtcStats"]["iceStats"].get("succeeded", [])
                        if pair["nominated"]]
            return bool(selected)

        # The client can report connected while getStats still returns the
        # nominated pair as in-progress, especially just after a reset.
        wait_until(nominated_pair_ready, timeout=30)
        assert selected, stats
        pair = selected[0]
        assert pair["remote"]["address"] == args.expected_rtc_host, pair
        assert pair["remote"]["port"] == args.expected_rtc_port, pair
        return stats["callID"], {
            "remote_host": pair["remote"]["address"], "remote_port": pair["remote"]["port"],
            "protocol": pair["remote"]["protocol"], "nominated": True,
            "packets_sent": pair["packetsSent"], "packets_received": pair["packetsReceived"],
        }

    def leave(page):
        page.locator("#calls-widget-leave-button").click()
        page.get_by_text("Leave call", exact=True).click()
        wait_until(lambda: page.evaluate("!window.callsClient"))

    def flow(browser, round_number):
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        try:
            page.goto(base + "/login")
            page.wait_for_timeout(3000)
            if page.get_by_text("View in Browser", exact=True).count():
                page.get_by_text("View in Browser", exact=True).click()
            page.locator("#input_loginId").fill("admin")
            page.locator("#input_password-input").fill("Admin@Secure123")
            page.locator("#saveSetting").click()
            page.wait_for_timeout(2500)
            page.goto(base + "/engineering/channels/deployments")
            page.wait_for_timeout(2000)
            close = page.get_by_role("button", name="Close", exact=True)
            if close.count():
                close.click()
            for username in args.recipients:
                open_dm(page, username)
                started = time.time_ns() // 1_000_000
                page.locator("#calls-join-button").click()
                channel, rtc = connected(page)
                page.screenshot(path=str(args.output / f"{round_number}-{username}-active.png"))
                # The 1.11 ended-post participants field is null (upstream
                # bug), so inspect the real active sessions during the wait.
                for _ in range(30):
                    active = session.get(base + "/plugins/com.mattermost.calls/" + channel, timeout=30)
                    active.raise_for_status()
                    call = active.json()["call"]
                    assert call["owner_id"] == caller
                    assert {s["user_id"] for s in call["sessions"]} == {caller}
                    page.wait_for_timeout(1000)
                connected(page)
                leave(page)
                wait_until(lambda: any(p.get("props", {}).get("end_at")
                                      for p in get_posts(channel) if p.get("create_at", 0) >= started))
                calls = [p for p in get_posts(channel)
                         if p["type"] == "custom_calls" and p["user_id"] == caller
                         and p["create_at"] >= started]
                valid = [p for p in calls if p["props"]["end_at"] - p["props"]["start_at"] >= 30_000]
                assert valid, calls
                callback = "Please call me back when you are available."
                page.locator("#post_textbox").fill(callback)
                page.locator("#post_textbox").press("Enter")
                wait_until(lambda: any(p["user_id"] == caller and p.get("message") == callback
                                      and p["create_at"] >= started for p in get_posts(channel)))
                page.screenshot(path=str(args.output / f"{round_number}-{username}-ended.png"))
                print(json.dumps({"round": round_number, "recipient": username, "rtc": rtc,
                                  "duration_ms": valid[0]["props"]["end_at"] - valid[0]["props"]["start_at"],
                                  "callback_saved": True}), flush=True)
            if args.reset_container and round_number == 1:
                # A live session must not survive restore; leaving first would
                # miss stale plugin state and listeners.
                page.locator("#calls-join-button").click()
                connected(page)
                reset_active_call(channel)
            return context
        except Exception:
            page.screenshot(path=str(args.output / f"{round_number}-failure.png"))
            (args.output / f"{round_number}-failure.txt").write_text(page.locator("body").inner_text())
            context.close()
            raise

    def reset_active_call(channel):
        name = args.reset_container
        pid1 = container_meta(name)["State"]["Pid"]
        old_child = docker("exec", name, "cat", "/run/webarena-mattermost.pid").stdout.strip()
        old_pg = docker("exec", name, "head", "-n", "1", "/mm/pgdata/postmaster.pid").stdout.strip()
        if args.delay_supervisor:
            docker("exec", name, "kill", "-STOP", "1")
        try:
            with (args.output / "reset.log").open("w") as log:
                reset = subprocess.Popen(["docker", "exec", name, "/usr/local/bin/webarena-reset-state"],
                                         stdout=log, stderr=subprocess.STDOUT)
                try:
                    if args.delay_supervisor:
                        wait_until(lambda: docker("exec", name, "test", "-e",
                                                  "/run/webarena-mattermost-resetting", check=False).returncode == 0)
                        time.sleep(1)
                        assert reset.poll() is None
                        assert docker("exec", name, "test", "-e", "/run/webarena-mattermost-stopped",
                                      check=False).returncode != 0
                        assert docker("exec", name, "head", "-n", "1",
                                      "/mm/pgdata/postmaster.pid").stdout.strip() == old_pg
                finally:
                    if args.delay_supervisor:
                        docker("exec", name, "kill", "-CONT", "1")
                assert reset.wait(timeout=180) == 0, (args.output / "reset.log").read_text()
        finally:
            if args.delay_supervisor:
                docker("exec", name, "kill", "-CONT", "1", check=False)
        new_child = docker("exec", name, "cat", "/run/webarena-mattermost.pid").stdout.strip()
        assert old_child != new_child
        assert container_meta(name)["State"]["Pid"] == pid1
        login_api()
        channels = session.get(base + "/api/v4/users/me/channels", timeout=30)
        channels.raise_for_status()
        if any(c["id"] == channel for c in channels.json()):
            assert not any(p["type"] == "custom_calls" for p in get_posts(channel))
        print(json.dumps({"reset": True, "pid1_preserved": True, "child_changed": True,
                          "calls_removed": True, "delayed_supervisor": args.delay_supervisor}), flush=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = flow(browser, 1)
            context.close()
            if args.reset_container:
                context = flow(browser, 2)
                context.close()
        finally:
            browser.close()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Exercise full Mattermost history in an isolated, disposable image fixture.

Requires Docker, requests, Playwright and its Chromium browser. Never resets an
existing container: this command creates and removes its own limited fixture.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import time
import uuid
from pathlib import Path

import requests
from playwright.sync_api import expect, sync_playwright

SITE = Path(__file__).resolve().parents[1]


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


def sql(container: str, query: str) -> str:
    return docker(
        "exec",
        container,
        "psql",
        "-U",
        "mmuser",
        "-d",
        "mattermost_test",
        "-Atc",
        query,
    )


def ready(url: str) -> None:
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        try:
            response = requests.get(url + "/api/v4/system/ping", timeout=5)
            if response.ok and response.json().get("status") == "OK":
                return
        except (requests.RequestException, ValueError):
            pass
        time.sleep(1)
    raise RuntimeError("Mattermost did not become ready within 120 seconds")


def api_session(url: str) -> requests.Session:
    session = requests.Session()
    response = session.post(
        url + "/api/v4/users/login",
        json={
            "login_id": "admin",
            "password": "Admin@Secure123",
        },
        timeout=30,
    )
    response.raise_for_status()
    session.headers["Authorization"] = "Bearer " + response.headers["Token"]
    return session


def api(session: requests.Session, url: str, path: str, **kwargs):
    response = session.request(
        "POST" if "json" in kwargs else "GET",
        url + "/api/v4" + path,
        timeout=30,
        **kwargs,
    )
    response.raise_for_status()
    return response.json()


def seed_state(container: str) -> dict:
    # Browser reads legitimately mark channels read. Check this before each UI
    # pass, so the second pass also proves native reset restores the task seed.
    total, posts = map(
        int,
        sql(
            container,
            "SELECT count(*), count(*) FILTER (WHERE deleteat = 0) FROM posts WHERE type = ''",
        ).split("|"),
    )
    assert (total, posts) == (31834, 31830), (
        f"User-message seed changed: {total} total, {posts} undeleted"
    )
    counts = sql(
        container,
        """
        SELECT count(*) FILTER (WHERE channel.type IN ('O','P')),
               count(*), sum(channel.totalmsgcount - membership.msgcount)
        FROM channelmembers membership
        JOIN users task_user ON task_user.id = membership.userid
        JOIN channels channel ON channel.id = membership.channelid
        WHERE task_user.username = 'admin'
    """,
    ).split("|")
    assert counts == ["14", "17", "8"], f"Task membership/unread seed changed: {counts}"
    fingerprint = sql(
        container,
        """
        SELECT md5(string_agg(id || ':' || userid || ':' || channelid || ':' || rootid || ':' || createat || ':' || deleteat || ':' || message, ',' ORDER BY id))
        FROM posts WHERE type = ''
    """,
    )
    return {
        "user_posts_total": total,
        "undeleted_user_posts": posts,
        "team_channels": 14,
        "conversations": 17,
        "unread": 8,
        "corpus_md5": fingerprint,
    }


def protected_posts(container: str, session: requests.Session, url: str) -> dict:
    verified = {}
    for expected in json.loads((SITE / "protected_task_messages.json").read_text()):
        post_id = expected["post_id"]
        if not expected["original_synthetic"]:
            assert post_id == "props:task_evidence_key=recent-emma-interaction"
            post_id = sql(
                container,
                "SELECT id FROM posts WHERE props ->> 'task_evidence_key' = 'recent-emma-interaction'",
            )
        actual = api(session, url, f"/posts/{post_id}")
        assert actual["message"] == expected["exact_message"], expected["evidence_id"]
        assert (
            hashlib.sha256(actual["message"].encode()).hexdigest() == expected["sha256"]
        )
        assert actual["create_at"] == expected["create_at_ms"]
        assert actual["delete_at"] == 0
        verified[expected["evidence_id"]] = actual
    return verified


def browser_history(
    url: str, posts: dict, session: requests.Session, artifacts: Path, phase: str
) -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.add_locator_handler(
            page.get_by_role("dialog", name=re.compile(r"^Mattermost .* is here!$")),
            lambda dialog: dialog.get_by_role(
                "button", name="Close", exact=True
            ).click(),
        )
        try:
            page.goto(url + "/login")
            page.get_by_text("View in Browser", exact=True).click()
            page.locator('input[type="text"]').fill("admin")
            page.locator('input[type="password"]').fill("Admin@Secure123")
            page.get_by_role("button", name="Log in", exact=True).click()
            page.wait_for_url("**/select_team")
            # Admin intentionally does not belong to town-square. Keep the
            # 14-channel/17-conversation seed and use an existing membership.
            page.goto(url + "/engineering/channels/project-alpha")
            expect(
                page.get_by_role("button").filter(
                    has_text=re.compile("Team Edition", re.IGNORECASE)
                )
            ).to_be_visible()
            # The report searched "authentication". That word occurs in the
            # parent post; E02 itself says "auth flow" and is one of its replies.
            page.locator("#searchFormContainer").click()
            search = page.get_by_placeholder("Search messages", exact=True)
            search.fill("in:project-alpha authentication")
            search.press("Enter")
            results = page.locator("#search-items-container")
            expect(results).to_contain_text("customer portal authentication flow")
            results.get_by_role("button").filter(has_text="6 replies").click()
            expect(page.locator("body")).to_contain_text(posts["E02"]["message"])
            expect(page.get_by_text("Restore Access", exact=False)).to_have_count(0)
            page.screenshot(path=str(artifacts / f"{phase}-authentication-thread.png"))
            for evidence, query in (
                ("E02", 'in:project-alpha "March 25"'),
                ("E01", 'in:deployments "Weekly Deployment Schedule"'),
            ):
                page.locator("#searchFormContainer").click()
                search = page.get_by_placeholder("Search messages", exact=True)
                search.fill(query)
                search.press("Enter")
                # E02 is the canonical task100 deadline reply. E01 covers a
                # separate older channel and a formatted schedule.
                text = (
                    "auth flow working end-to-end by March 25"
                    if evidence == "E02"
                    else "Payment Gateway"
                )
                expect(page.locator("#search-items-container")).to_contain_text(text)
                expect(page.get_by_text("Restore Access", exact=False)).to_have_count(0)
                page.screenshot(path=str(artifacts / f"{phase}-{evidence}-search.png"))
                # Open the actual post/thread, not just a search-result snippet.
                page.goto(url + "/engineering/pl/" + posts[evidence]["id"])
                expect(page.locator("body")).to_contain_text(text)
                expect(page.get_by_text("Restore Access", exact=False)).to_have_count(0)
                page.screenshot(path=str(artifacts / f"{phase}-{evidence}-post.png"))
            emma_channel = api(session, url, "/channels/" + posts["E19"]["channel_id"])
            page.goto(url + "/engineering/channels/" + emma_channel["name"])
            expect(page.locator("body")).to_contain_text("emma.davis")
            expect(page.locator("body")).to_contain_text("welcome, please see")
            expect(page.get_by_text("Restore Access", exact=False)).to_have_count(0)
            expect(page.locator("#post_textbox")).to_be_editable()
            page.screenshot(path=str(artifacts / f"{phase}-E19-emma.png"))
        except BaseException:
            page.screenshot(path=str(artifacts / f"{phase}-failure.png"))
            raise
        finally:
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--image",
        required=True,
        help="Locally built image or immutable published digest",
    )
    parser.add_argument("--artifacts-dir", type=Path, required=True)
    args = parser.parse_args()
    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    report_path = args.artifacts_dir / "report.json"
    report_path.unlink(missing_ok=True)
    name = "webarena-mm-history-" + uuid.uuid4().hex[:12]
    docker(
        "run",
        "-d",
        "--name",
        name,
        "--label",
        "webarena.validation=mattermost-history",
        "--cpus=1.5",
        "--memory=3g",
        "-p",
        "127.0.0.1::8065",
        args.image,
    )
    try:
        report = {
            "image": args.image,
            "image_id": docker("inspect", "--format", "{{.Image}}", name),
            "phases": {},
        }
        port = docker("port", name, "8065/tcp").rsplit(":", 1)[1]
        url = "http://127.0.0.1:" + port
        ready(url)
        previous = None
        for phase in ("initial", "after-reset"):
            if phase == "after-reset":
                docker("exec", name, "/usr/local/bin/webarena-reset-state")
                ready(url)
            state = seed_state(name)
            if previous is not None:
                assert state == previous, "Reset did not restore complete seed"
            previous = state
            with api_session(url) as session:
                config = api(session, url, "/config/client?format=old")
                assert config["BuildEnterpriseReady"] == "false", (
                    "History fixture must use Team Edition, not capped Entry Edition"
                )
                posts = protected_posts(name, session, url)
                browser_history(url, posts, session, args.artifacts_dir, phase)
                report["phases"][phase] = {
                    **state,
                    "protected_posts": len(posts),
                    "version": config["Version"],
                    "edition": "Team",
                    "browser": "Chromium",
                }
                if phase == "initial":
                    api(
                        session,
                        url,
                        "/posts",
                        json={
                            "channel_id": posts["E02"]["channel_id"],
                            "message": "Disposable history reset verification marker",
                        },
                    )
            print(
                f"{phase}: full corpus, all 19 protected posts, E01/E02 search/read and Emma DM passed",
                flush=True,
            )
        report_path.write_text(json.dumps(report, indent=2) + "\n")
    finally:
        try:
            (args.artifacts_dir / "container.log").write_text(docker("logs", name))
        finally:
            docker("rm", "-f", name)


if __name__ == "__main__":
    main()

"""Opt-in real-browser editor regression; never uses existing benchmark containers.

python test_text_editor.py --image webarenapro/nextcloud:latest --evidence-dir /tmp/nc-text
Requires Docker, requests, Playwright, and its Chromium installation.
"""
from __future__ import annotations

import argparse
import json
import socket
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import docker
import requests
from playwright.sync_api import sync_playwright

OWNER_LABEL = "webarena.nextcloud.text-smoke"


def safe_url(value):
    parsed = urlsplit(value)
    # Session keys and request tokens can occur in Nextcloud request URLs.
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))


def wait_for(predicate, *, timeout, description):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            result = predicate()
            if result:
                return result
        except requests.RequestException as error:
            last_error = type(error).__name__
        time.sleep(0.5)
    raise AssertionError(f"Timed out after {timeout}s: {description}; last error={last_error}")


def exercise_editor(browser, base_url, local_url, evidence, phase):
    context = browser.new_context(viewport={"width": 1440, "height": 1000})
    page = context.new_page()
    page.set_default_timeout(30_000)
    diagnostics = {"phase": phase, "browser": browser.version, "errors": [], "http_errors": [], "request_failures": []}
    page.on("pageerror", lambda error: diagnostics["errors"].append({"message": str(error), "stack": error.stack}))
    page.on("response", lambda response: diagnostics["http_errors"].append(
        {"url": safe_url(response.url), "status": response.status}
    ) if response.status >= 400 else None)
    page.on("requestfailed", lambda request: diagnostics["request_failures"].append(
        {"url": safe_url(request.url), "failure": request.failure}
    ))
    filename = "text-editor-smoke.md"
    text = f"Client Meeting Update\nPersisted editor content {phase}."
    file_url = f"{local_url}/remote.php/dav/files/maya.patel/{filename}"
    try:
        page.goto(f"{base_url}/login", wait_until="domcontentloaded")
        page.locator("#user").fill("maya.patel")
        page.locator("#password").fill("agentpass")
        page.locator("button[type=submit]").click()
        page.wait_for_url("**/apps/**")
        page.goto(f"{base_url}/apps/files/", wait_until="domcontentloaded")
        page.get_by_role("button", name="New", exact=True).click()
        page.get_by_text("New text file", exact=True).click()
        page.get_by_role("textbox", name="Filename").fill(filename)
        page.get_by_role("button", name="Create", exact=True).click()
        editor = page.locator('[contenteditable="true"]').first
        editor.wait_for(state="visible", timeout=30_000)
        editor.click()
        editor.press_sequentially(text, delay=10)
        editor_url = page.url
        assert "openfile=true" in editor_url, editor_url
        # Closing the viewer flushes the collaborative Text session to WebDAV.
        page.get_by_role("button", name="Save document", exact=True).click()
        page.locator("button[aria-label=Close]:visible").first.click()
        editor.wait_for(state="hidden", timeout=10_000)
        def saved():
            response = requests.get(file_url, auth=("maya.patel", "agentpass"), timeout=5)
            diagnostics["last_dav_status"] = response.status_code
            diagnostics["last_dav_text"] = response.text[:3000]
            return response.status_code == 200 and all(line in response.text for line in text.splitlines())
        wait_for(
            saved,
            timeout=30, description="editor save observed through WebDAV",
        )
        page.goto(f"{base_url}/apps/files/", wait_until="domcontentloaded")
        page.goto(editor_url, wait_until="domcontentloaded")
        editor.wait_for(state="visible", timeout=30_000)
        wait_for(lambda: phase in editor.inner_text(), timeout=15, description="saved text after reopening")
        page.screenshot(path=str(evidence / f"{phase}-saved.png"))
        diagnostics["result"] = "passed"
    except Exception:
        diagnostics["result"] = "failed"
        diagnostics["url"] = safe_url(page.url)
        try:
            page.screenshot(path=str(evidence / f"{phase}-failure.png"), timeout=5000)
        except Exception:
            pass
        raise
    finally:
        (evidence / f"{phase}-browser.json").write_text(json.dumps(diagnostics, indent=2))
        context.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, help="Existing local image; this test never pulls")
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    client = docker.from_env(timeout=300)
    image = client.images.get(args.image)
    name = f"nc-text-smoke-{uuid.uuid4().hex[:12]}"
    labels = {OWNER_LABEL: name}
    volume = None
    container = None
    # A worker-like .localhost origin exercises browser origin handling, without
    # changing DNS, the shared proxy, or any application container/network.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    hostname = f"{name}.localhost"
    base_url = f"http://{hostname}:{port}"
    local_url = f"http://127.0.0.1:{port}"
    try:
        volume = client.volumes.create(f"{name}-html", labels=labels)
        container = client.containers.run(
            image.id, name=name, detach=True, labels=labels,
            mem_limit="3g", nano_cpus=1_500_000_000,
            ports={"80/tcp": ("127.0.0.1", port)},
            mounts=[docker.types.Mount("/var/www/html", volume.name, type="volume", no_copy=True)],
            environment={"WP_NEXTCLOUD_URL": base_url, "WP_NEXTCLOUD_HOST_PORT": "80"},
        )
        metadata = {"image": image.id, "repo_digests": image.attrs.get("RepoDigests", []), "container": container.id, "origin": base_url}
        (args.evidence_dir / "runtime.json").write_text(json.dumps(metadata, indent=2))
        wait_for(lambda: requests.get(f"{local_url}/login", timeout=5).status_code == 200,
                 timeout=180, description="fresh-volume login readiness")
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(args=[f"--host-resolver-rules=MAP {hostname} 127.0.0.1", "--disable-dev-shm-usage"])
            try:
                exercise_editor(browser, base_url, local_url, args.evidence_dir, "fresh")
                result = container.exec_run(("timeout", "--kill-after=5", "180", "bash", "/usr/local/bin/webarena-reset-state"))
                (args.evidence_dir / "reset.log").write_bytes(result.output)
                assert result.exit_code == 0, "reset failed; see reset.log"
                response = requests.get(f"{local_url}/remote.php/dav/files/maya.patel/text-editor-smoke.md", auth=("maya.patel", "agentpass"), timeout=10)
                assert response.status_code == 404, "reset must remove the pre-reset test file"
                exercise_editor(browser, base_url, local_url, args.evidence_dir, "reset")
            finally:
                browser.close()
        print(f"PASS: editor create/edit/save/reopen before and after reset; evidence {args.evidence_dir}")
    finally:
        cleanup_errors = []
        if container is not None:
            try:
                (args.evidence_dir / "container.log").write_bytes(container.logs(tail=300))
                result = container.exec_run(("tail", "-100", "/var/www/html/data/nextcloud.log"))
                (args.evidence_dir / "nextcloud.log").write_bytes(result.output)
            except Exception as error:
                cleanup_errors.append(f"Diagnostics: {type(error).__name__}: {error}")
            try:
                container.reload()
                if container.labels.get(OWNER_LABEL) == name:
                    container.remove(force=True)
            except Exception as error:
                cleanup_errors.append(f"Container cleanup: {type(error).__name__}: {error}")
        if volume is not None:
            try:
                if volume.attrs.get("Labels", {}).get(OWNER_LABEL) == name:
                    volume.remove()
            except Exception as error:
                cleanup_errors.append(f"Volume cleanup: {type(error).__name__}: {error}")
        if cleanup_errors:
            (args.evidence_dir / "cleanup-errors.json").write_text(json.dumps(cleanup_errors, indent=2))
            print(f"Cleanup/diagnostic errors: {cleanup_errors}")
        client.close()
        if any("cleanup:" in error for error in cleanup_errors) and sys.exc_info()[0] is None:
            raise RuntimeError("Owned fixture cleanup failed; see cleanup-errors.json")


if __name__ == "__main__":
    main()

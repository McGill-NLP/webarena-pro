"""Explicit installation of the locked Node MCP runtime."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

MCP_VERSION = "0.0.84"
PLAYWRIGHT_VERSION = "1.64.1"


def runtime_dir() -> Path:
    lock = Path(__file__).with_name("runtime") / "package-lock.json"
    digest = hashlib.sha256(lock.read_bytes()).hexdigest()[:16]
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "webarena-pro-mcp" / digest


def server_path() -> Path:
    path = runtime_dir() / "node_modules/@playwright/mcp/cli.js"
    if not path.is_file() or not shutil.which("node"):
        raise RuntimeError("Run `webarena-pro-mcp install` to install the pinned MCP runtime and Chromium")
    return path


def preflight() -> None:
    server_path()
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        if not Path(playwright.chromium.executable_path).is_file():
            raise RuntimeError("Pinned Chromium is missing; run `webarena-pro-mcp install`")


def install() -> None:
    if not shutil.which("npm"):
        raise RuntimeError("Node.js and npm are required")
    target = runtime_dir()
    target.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(Path(__file__).with_name("runtime") / name, target / name)
    subprocess.run(["npm", "ci", "--ignore-scripts", "--prefix", str(target)], check=True)
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)

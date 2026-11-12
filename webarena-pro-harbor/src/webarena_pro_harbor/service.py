"""Persist private service diagnostics independently of browser initialization."""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import threading
import traceback
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from webarena_pro_mcp.artifacts import atomic_json

DIAGNOSTICS = "/webarena-service"


def redact(text):
    """Sanitize before writing; never save raw subprocess output to disk."""
    for key, value in sorted(os.environ.items(), key=lambda item: len(item[1]), reverse=True):
        if value and re.search(r"TOKEN|PASSWORD|SECRET|API_KEY", key, re.I):
            text = text.replace(value, "<redacted>")
    # Drop URL userinfo and all queries/fragments (including signed URLs).
    text = re.sub(r"(https?://)[^/\s@]+@", r"\1<redacted>@", text, flags=re.I)
    text = re.sub(r"(https?://[^\s?#]+)[?#][^\s]*", r"\1?<redacted>", text, flags=re.I)
    # Headers can contain multiple cookie pairs or authentication parameters;
    # redact the whole remaining line, not only the first whitespace token.
    text = re.sub(
        r"(?im)((?:authorization|proxy-authorization|cookie|set-cookie)\s*[:=]\s*)[^\r\n]*",
        r"\1<redacted>", text,
    )
    text = re.sub(
        r'''(?i)(["']?(?:password|passwd|token|access_token|refresh_token|api[_-]?key|secret|authorization|cookie|set-cookie)["']?\s*[:=]\s*)(?:"[^"\n]*"|'[^'\n]*'|[^\s,;}]+(?:\s+[^\s,;}]+)?)''',
        r"\1<redacted>", text,
    )
    return text


def now():
    return datetime.now(timezone.utc).isoformat()


def append(path, value):
    with path.open("a", encoding="utf-8") as handle:
        os.chmod(path, 0o600)
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())


def healthcheck(directory, port):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as response:
            if response.status != 200 or json.load(response).get("ready") is not True:
                raise RuntimeError("Browser health endpoint is not ready")
        if not (directory / "ready.json").exists():
            atomic_json(directory / "ready.json", {"ready": True, "at": now()})
        return 0
    except Exception as exc:
        # No response body, credentials, or remote URLs enter the health log.
        append(directory / "health.jsonl", json.dumps({
            "at": now(), "ready": False, "error": redact(f"{type(exc).__name__}: {exc}"),
        }) + "\n")
        return 1


def supervise(config, evidence, socket, port, diagnostics=DIAGNOSTICS):
    os.umask(0o077)
    directory = Path(diagnostics)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    # A stale marker must not make a failed new launch look ready.
    (directory / "ready.json").unlink(missing_ok=True)
    atomic_json(directory / "status.json", {"status": "starting", "started_at": now()})
    for name in ("stdout.log", "stderr.log"):
        append(directory / name, "")
    command = [sys.executable, "-u", "-m", "webarena_pro_harbor.service", str(config),
               str(evidence), str(socket), str(port)]
    last_error = []
    process = None
    handlers = {}
    threads = []

    def capture(stream, filename, output):
        # Bound individual records. Oversized lines are discarded in their
        # entirety, so a credential split at the limit cannot escape redaction.
        with stream:
            while raw := stream.readline(65537):
                if len(raw) > 65536:
                    while raw and not raw.endswith("\n"):
                        raw = stream.readline(65537)
                    clean = "<oversized diagnostic line omitted>\n"
                else:
                    clean = redact(raw)
                append(directory / filename, clean)
                try:
                    output.write(clean)
                    output.flush()
                except (OSError, ValueError):
                    pass
                if filename == "stderr.log" and clean.strip():
                    last_error[:] = [clean.strip()[:4000]]

    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace")
        for sig in (signal.SIGTERM, signal.SIGINT):
            handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, lambda received, _frame: process.send_signal(received))
        for stream, name, output in ((process.stdout, "stdout.log", sys.stdout),
                                     (process.stderr, "stderr.log", sys.stderr)):
            thread = threading.Thread(target=capture, args=(stream, name, output), daemon=True)
            thread.start()
            threads.append(thread)
        code = process.wait()
        # The service owns and closes its children before it exits. Bound pipe
        # draining if an unexpected descendant retains an inherited descriptor.
        for thread in threads:
            thread.join(timeout=5)
    except BaseException as exc:
        last_error[:] = [redact(f"{type(exc).__name__}: {exc}")]
        append(directory / "stderr.log", last_error[0] + "\n")
        code = 1
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    finally:
        for sig, handler in handlers.items():
            signal.signal(sig, handler)
    ready = (directory / "ready.json").exists()
    state = {
        "schema_version": 1,
        "status": "stopped" if ready and code == 0 else ("service_error" if ready else "setup_error"),
        "ready": ready, "exit_code": code, "finished_at": now(),
    }
    if code < 0:
        state["signal"] = -code
    if last_error and (code != 0 or not ready):
        state["error"] = last_error[0]
    atomic_json(directory / "status.json", state)
    if not ready:
        # Never invent a zero reward for infrastructure failure. This remains
        # available even when no private Core evidence directory was created.
        atomic_json(directory / "result.json", {**state, "steps": 0, "graded": False})
    return code if code >= 0 else 128 - code


def worker(config, evidence, socket, port):
    try:
        from webarena_pro_mcp.server import serve

        asyncio.run(serve(Path(config), Path(evidence), Path(socket), int(port), host="0.0.0.0"))
    except BaseException as exc:
        # Trace locations are useful; source lines and locals may contain secrets.
        # Preserve nested/causal startup errors rather than only a TaskGroup's
        # uninformative outer message.
        seen = set()

        def report(error):
            if id(error) in seen:
                return
            seen.add(id(error))
            cause = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
            if cause is not None:
                report(cause)
            if isinstance(error, BaseExceptionGroup):
                for child in error.exceptions:
                    report(child)
            for frame in traceback.extract_tb(error.__traceback__):
                print(f"  {frame.filename}:{frame.lineno} in {frame.name}", file=sys.stderr)
            print(redact(f"{type(error).__name__}: {error}"), file=sys.stderr)

        report(exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(worker(*sys.argv[1:]))

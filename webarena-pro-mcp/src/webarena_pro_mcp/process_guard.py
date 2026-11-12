"""MCP stdio launcher: its separate kill scope must not outlive its worker."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def main():
    if os.name != "posix" or os.getpgrp() != os.getpid():
        raise RuntimeError("The MCP guardian requires its own POSIX process group")
    parent = os.getppid()
    path = Path.cwd() / "mcp-process.json"
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as handle:
        os.chmod(temporary, 0o600)
        json.dump({"parent_pid": parent, "pgid": os.getpgrp()}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    temporary.replace(path)
    child = subprocess.Popen(sys.argv[1:])  # Inherit this MCP session/stdio.
    while child.poll() is None:
        if os.getppid() != parent:
            os.killpg(os.getpgrp(), signal.SIGKILL)
        time.sleep(0.1)
    return child.returncode


if __name__ == "__main__":
    raise SystemExit(main())

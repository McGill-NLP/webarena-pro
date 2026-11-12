"""Private, append-only attempt artifacts; never model-accessible as files."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


def atomic_json(path: Path, value) -> None:
    """Atomically persist private session state and evaluation evidence."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        os.chmod(tmp, 0o600)
        json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    tmp.replace(path)
    if os.name == "posix":
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def safe_error(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        return "; ".join(safe_error(child) for child in exc.exceptions)
    message = f"{type(exc).__name__}: {exc}"
    for key, value in os.environ.items():
        if value and re.search(r"(?:TOKEN|PASSWORD|SECRET|API_KEY)", key, re.I):
            message = message.replace(value, "<redacted>")
    message = re.sub(r"(?i)((?:token|password|api_key)=)[^&\s]+", r"\1<redacted>", message)
    return message[:4000]


class Artifacts:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=False, mode=0o700)
        root.chmod(0o700)

    def write(self, name: str, value) -> None:
        atomic_json(self.root / name, value)

    def append(self, name: str, value) -> None:
        path = self.root / name
        with path.open("a", encoding="utf-8") as handle:
            os.chmod(path, 0o600)
            handle.write(json.dumps(value, ensure_ascii=False, allow_nan=False) + "\n")
            handle.flush()
            os.fsync(handle.fileno())

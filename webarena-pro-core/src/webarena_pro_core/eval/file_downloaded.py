"""DAG node evaluator: verify the agent triggered a browser download.

Reads downloads captured during ``task.setup()`` (listener in
``WebArenaProTask``) from ``EvalContext.downloads``. Each entry is a dict with
``path`` (local file), ``suggested_filename``, and ``url``.

Supported ``eval_config`` keys (all optional - the defaults only enforce that
something was downloaded):

- ``filename_regex``: regex matched against ``suggested_filename`` (or basename
  when the suggested filename is missing). Case-sensitive; use ``(?i)`` inline.
- ``extension``: required suffix on the suggested filename (e.g. ``.pdf``).
- ``magic_bytes``: ascii/utf-8 prefix the file must start with (e.g. ``%PDF-``).
- ``min_size_bytes``: file must be at least this large (default: 1).
- ``expected_md5``: lowercase hex md5 of the file contents. PDFs with embedded
  timestamps won't match; only set this for deterministic exports (CSV, etc).

A download passes when *all configured* checks pass. The node returns True if
at least one download passes.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from webarena_pro_core.eval.dag import EvalContext

logger = logging.getLogger(__name__)


def _magic_matches(path: str, prefix: str) -> bool:
    needle = prefix.encode("utf-8") if isinstance(prefix, str) else bytes(prefix)
    try:
        with open(path, "rb") as f:
            head = f.read(len(needle))
    except OSError:
        return False
    return head == needle


def _md5(path: str) -> str | None:
    try:
        h = hashlib.md5()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _check_one(dl: dict, cfg: dict) -> tuple[bool, str]:
    path = dl.get("path") or ""
    suggested = dl.get("suggested_filename") or (os.path.basename(path) if path else "")

    if not path or not os.path.exists(path):
        return False, "missing path"

    size = os.path.getsize(path)
    min_size = int(cfg.get("min_size_bytes", 1))
    if size < min_size:
        return False, f"size {size} < {min_size}"

    if "filename_regex" in cfg:
        pat = cfg["filename_regex"]
        if not re.search(pat, suggested):
            return False, f"filename {suggested!r} !~ /{pat}/"

    if "extension" in cfg:
        ext = cfg["extension"]
        if not suggested.endswith(ext):
            return False, f"filename {suggested!r} does not end with {ext}"

    if "magic_bytes" in cfg:
        if not _magic_matches(path, cfg["magic_bytes"]):
            return False, f"magic bytes mismatch (expected {cfg['magic_bytes']!r})"

    if "expected_md5" in cfg:
        digest = _md5(path)
        if digest != str(cfg["expected_md5"]).lower():
            return False, f"md5 {digest} != {cfg['expected_md5']}"

    return True, f"ok (size={size}, name={suggested!r})"


class FileDownloadedEvaluator:
    """Evaluate whether a browser download matching configured constraints exists.

    The task wrapper records Playwright downloads into
    :attr:`~webarena_pro_core.eval.dag.EvalContext.downloads`. This evaluator
    checks those captured files against optional filename, extension, magic
    byte, size, and MD5 constraints. It passes when at least one captured
    download satisfies every configured constraint.
    """

    def evaluate(self, eval_config: dict, context: "EvalContext"):
        from webarena_pro_core.eval.dag import NodeResult

        downloads = context.downloads or []
        if not downloads:
            return NodeResult(passed=False, reason="no downloads captured during run")

        rejections: list[str] = []
        for dl in downloads:
            name = dl.get("suggested_filename") or dl.get("path") or "<unknown>"
            ok, reason = _check_one(dl, eval_config)
            logger.info(
                "file_downloaded candidate %s: %s (%s)",
                name,
                "PASS" if ok else "FAIL",
                reason,
            )
            if ok:
                return NodeResult(passed=True, reason=f"{name}: {reason}")
            rejections.append(f"{name}: {reason}")

        return NodeResult(
            passed=False,
            reason=f"no download matched config; rejected: {rejections}",
        )

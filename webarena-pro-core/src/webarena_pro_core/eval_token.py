"""Shared authentication for read-only benchmark evaluation endpoints."""

from __future__ import annotations

import os
from pathlib import Path
import secrets
import tempfile


class EvalTokenConfigurationError(ValueError):
    """Invalid or inaccessible configuration, without including the secret."""


def _validate_token(token: str, *, source: str = "WP_EVAL_TOKEN") -> str:
    if not token or any(not 33 <= ord(character) <= 126 for character in token):
        raise EvalTokenConfigurationError(
            f"eval_token_configuration_error: {source} must contain a nonempty "
            "printable ASCII token without whitespace. Correct this configuration "
            "and use the same token for containers and evaluator."
        )
    return token


def resolve_eval_token() -> str:
    """Return an explicit token or atomically provision a persistent user token.

    No process cache or worker namespace: separate CLI invocations and spawned
    workers must agree. A temporary file is completely written before a hard
    link publishes it; concurrent creators read the winner's complete file.
    Existing files are never replaced, including invalid/empty files.
    """
    if "WP_EVAL_TOKEN" in os.environ:
        return _validate_token(os.environ["WP_EVAL_TOKEN"])

    configured_path = os.environ.get("WP_EVAL_TOKEN_FILE")
    if configured_path is not None and not configured_path.strip():
        raise EvalTokenConfigurationError(
            "eval_token_configuration_error: WP_EVAL_TOKEN_FILE must name a file."
        )
    config_home = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    path = (
        Path(configured_path).expanduser()
        if configured_path is not None
        else config_home / "webarena-pro" / "eval-token"
    )
    try:
        try:
            return _validate_token(path.read_text(encoding="ascii").strip(), source="the shared token file")
        except FileNotFoundError:
            pass

        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # NamedTemporaryFile requests owner-only permissions (mode 0600).
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".eval-token-", mode="w") as temp:
            temp.write(secrets.token_urlsafe(32) + "\n")
            temp.flush()
            os.fsync(temp.fileno())
            try:
                os.link(temp.name, path)
            except FileExistsError:
                pass  # Another process published the shared token first.
        return _validate_token(path.read_text(encoding="ascii").strip(), source="the shared token file")
    except (OSError, UnicodeError) as error:
        raise EvalTokenConfigurationError(
            "eval_token_configuration_error: cannot read or provision the shared "
            "token file. Check WP_EVAL_TOKEN_FILE / XDG_CONFIG_HOME permissions, "
            "or set the same WP_EVAL_TOKEN for containers and evaluator."
        ) from error

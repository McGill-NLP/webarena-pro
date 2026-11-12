"""WebArena-Pro package initialization."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def done() -> None:
    """
    Mark the task as complete.

    Examples:
        done()
    """
    pass


def _register_done_action() -> None:
    """Register a `done()` action in BrowserGym high-level action subsets.

    This keeps GenericAgent compatible with prompts that emit `done()` and
    makes task completion explicit in the action space.
    """
    try:
        import browsergym.core.action.highlevel as highlevel  # type: ignore[import-not-found]

        target_subsets = ("bid", "webarena", "visualwebarena", "workarena", "workarena++")

        for subset in target_subsets:
            if subset not in highlevel.ACTION_SUBSETS:
                continue

            actions = list(highlevel.ACTION_SUBSETS[subset])
            if any(action.__name__ == "done" for action in actions):
                continue

            actions.append(done)
            highlevel.ACTION_SUBSETS[subset] = actions

    except Exception as exc:  # pragma: no cover - defensive import-time guard
        logger.debug("Could not register BrowserGym done action: %s", exc)


_register_done_action()


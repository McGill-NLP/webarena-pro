"""Completion detection for BrowserGym high-level actions."""

from browsergym.core.action.parsers import highlevel_action_parser
from pyparsing import ParseBaseException


_COMPLETION_ACTIONS = {"done", "send_msg_to_user", "report_infeasible"}


def is_completion_action(action: str | None) -> bool:
    """Check parsed call names, without treating argument text as an action."""
    if not action:
        return False

    try:
        # Match HighLevelActionSet's non-strict parsing, including multi-action
        # input and code fences. The parser consumes arguments and skips comments.
        matches = highlevel_action_parser.search_string(action)
    except (ParseBaseException, SyntaxError, ValueError):
        return False

    return any(
        name in _COMPLETION_ACTIONS for calls in matches for name, _arguments in calls
    )

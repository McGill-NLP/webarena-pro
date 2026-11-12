"""Parse browser observations without any model or agent dependency."""

import re


def active_tab(text: str) -> tuple[int, str]:
    # MCP may repeat the same listing in both Result and Open tabs sections.
    # Only identical lines are duplicates; conflicting tabs still fail closed.
    current_lines = {
        line for line in text.splitlines()
        if re.match(r"^- \d+:\s*\(current\)\s*\[", line)
    }
    if len(current_lines) != 1:
        raise RuntimeError("Ambiguous MCP active-tab listing")
    match = re.match(r"- (\d+):\s*\(current\)\s*\[.*\]\((.*)\)\s*$", next(iter(current_lines)))
    if match:
        return int(match[1]), match[2]
    raise RuntimeError("Cannot identify the current MCP tab for grading")



def observation_url(text: str) -> str:
    match = re.search(r"^- Page URL: (.+)$", text, flags=re.M)
    return match[1] if match else ""

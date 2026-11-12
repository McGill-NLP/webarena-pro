"""Top-level `webarena-pro run` command helpers."""

from __future__ import annotations

import argparse
import sys

run_dashboard_main = None
run_tiered_main = None


def build_parser() -> argparse.ArgumentParser:
    from webarena_pro_bgym.run_tiered_cli import build_parser as build_eval_parser

    parser = build_eval_parser()
    parser.prog = "webarena-pro run"
    parser.description = "Run WebArena-Pro tiered evals or open the local worker/study dashboard."
    parser.epilog = (
        "Examples:\n"
        "  webarena-pro run --split dev --site nextcloud --task 172,173\n"
        "  webarena-pro run --site mattermost --n-jobs 2\n"
        "  webarena-pro run --split dev\n"
        "  webarena-pro run --split test --list\n"
        "  webarena-pro run --n-jobs 6 --agent-model gemini/gemini-3.5-flash\n"
        "  webarena-pro run --resume-study ~/agentlab_results/<study_dir>\n"
        "  webarena-pro run dashboard --study-dir ~/agentlab_results/<study_dir>\n"
        "  webarena-pro run -h\n"
        "  webarena-pro run dashboard -h"
    )
    parser.formatter_class = argparse.RawDescriptionHelpFormatter
    return parser


def _run_dashboard(argv: list[str]) -> int:
    global run_dashboard_main
    if run_dashboard_main is None:
        from webarena_pro_bgym.run_dashboard_cli import main as loaded_main

        run_dashboard_main = loaded_main

    return int(run_dashboard_main(argv))


def _run_tiered(argv: list[str]) -> int:
    global run_tiered_main
    if run_tiered_main is None:
        from webarena_pro_bgym.run_tiered_cli import main as loaded_main

        run_tiered_main = loaded_main

    return int(run_tiered_main(argv))


def main(argv: list[str] | None = None) -> int:
    forwarded = list(sys.argv[1:] if argv is None else argv)
    if not forwarded or forwarded in (["-h"], ["--help"]):
        build_parser().print_help()
        return 0

    if forwarded[0] == "help":
        build_parser().error(
            "the 'help' subcommand was removed; use '-h/--help' after the "
            "command instead, e.g. 'webarena-pro run -h' or "
            "'webarena-pro run dashboard -h'"
        )

    if forwarded[0] == "dashboard":
        return _run_dashboard(forwarded[1:])

    if forwarded[0] in {"eval", "tiered"}:
        build_parser().error(
            f"the {forwarded[0]} subcommand was removed; "
            "use webarena-pro run [options]; all tasks use tiered evaluation"
        )

    return _run_tiered(forwarded)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

#!/usr/bin/env python

from __future__ import annotations

import argparse
from pathlib import Path

import uvicorn

from webarena_pro_bgym.dashboard import create_dashboard_app, default_results_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the WebArena-Pro local progress dashboard")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind")
    parser.add_argument(
        "--results-root",
        type=Path,
        default=default_results_root(),
        help="AgentLab results root to scan",
    )
    parser.add_argument(
        "--study-dir",
        type=Path,
        default=None,
        help="Optional study dir to open by default",
    )
    args = parser.parse_args(argv)

    app = create_dashboard_app(results_root=args.results_root, default_study=args.study_dir)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

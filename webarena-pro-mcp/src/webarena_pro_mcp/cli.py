"""Install and serve the browser/media runtime for external MCP clients."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path


def parser():
    p = argparse.ArgumentParser(description="Agent-independent WebArena Pro MCP runtime")
    commands = p.add_subparsers(dest="command", required=True)
    commands.add_parser("install", help="Install locked Playwright MCP and Chromium")
    service = commands.add_parser("serve", help="Serve one browser session over Streamable HTTP MCP")
    service.add_argument("--config", type=Path, required=True, help="Private task, site URLs, and session limits")
    service.add_argument("--directory", type=Path, required=True, help="New private evidence directory")
    service.add_argument("--socket", type=Path, required=True, help="Private Unix socket for finalization")
    service.add_argument("--host", default="127.0.0.1")
    service.add_argument("--port", type=int, default=8000)
    finish = commands.add_parser("finalize", help="Private grading hook for the external orchestrator")
    finish.add_argument("--socket", type=Path, required=True)
    finish.add_argument("--timeout", type=float, default=360)
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    try:
        if args.command == "install":
            from .runtime import install

            install()
        elif args.command == "serve":
            from .server import serve

            if not 1 <= args.port <= 65535:
                raise ValueError("port must be between 1 and 65535")
            asyncio.run(serve(args.config, args.directory, args.socket, args.port, host=args.host))
        else:
            import math

            from .server import finalize

            if not math.isfinite(args.timeout) or args.timeout <= 0:
                raise ValueError("timeout must be finite and positive")
            asyncio.run(finalize(args.socket, args.timeout))
    except (ValueError, RuntimeError, OSError) as exc:
        p.exit(1, f"Error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
